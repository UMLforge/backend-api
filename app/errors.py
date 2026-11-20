"""One error shape for every failure, so the UI can always show a clear popup:

    {"error": {"title": "...", "message": "...", "hint": "...", "details": "..."}}

title, message, hint = written for END USERS: plain language, no URLs, env vars or commands.
details              = for developers/admins (shown collapsed under "Technical details").
"""
import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("umlforge.errors")

# Developer details (hostnames, settings, causes) stay on the server unless EXPOSE_ERROR_DETAILS=true (local dev).
# Admins always see them in the monitoring dashboard's error log, and they are logged.
EXPOSE_DETAILS = os.getenv("EXPOSE_ERROR_DETAILS", "false").lower() in ("1", "true", "yes")


def public_details(details: str) -> str:
    return details if EXPOSE_DETAILS else ""


class AppError(Exception):
    def __init__(self, status: int, title: str, message: str = "", hint: str = "", details: str = ""):
        super().__init__(details or message or title)
        self.status, self.title, self.message, self.hint, self.details = status, title, message, hint, details

    def public(self) -> dict:
        return {"title": self.title, "message": self.message, "hint": self.hint, "details": self.details}


def error_response(status: int, title: str, message: str = "", hint: str = "", details: str = "") -> JSONResponse:
    if details:
        log.info("%s %s | %s", status, title, details)
    return JSONResponse(status_code=status, content={"error": {
        "title": title, "message": message, "hint": hint, "details": public_details(details)}})


def _record(status: int, path: str, title: str, details: str, level: str = "error") -> None:
    """Sends failures to the monitoring dashboard (backend only; the ai-service has no dashboard)."""
    try:
        from .monitoring import record_error
    except ImportError:
        return
    record_error(status, path, title, details, level)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, e: AppError):
        if e.status >= 500 or e.status == 429:
            _record(e.status, request.url.path, e.title, e.details, "error" if e.status >= 500 else "warning")
        return error_response(e.status, e.title, e.message, e.hint, e.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, e: StarletteHTTPException):
        if e.status_code == 404:
            return error_response(404, "Not found", "That item doesn't exist (any more).",
                                  "Refresh the page and try again.", f"{request.method} {request.url.path}: {e.detail}")
        return error_response(e.status_code, "That didn't work", "The request couldn't be completed.",
                              "Please try again.", f"HTTP {e.status_code}: {e.detail}")

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return error_response(422, "This diagram couldn't be read", "Some of its data is missing or in the wrong format.",
                              "Try exporting it again, or start a new diagram.",
                              f"Validation failed at {where or 'request'}: {first.get('msg', 'invalid value')}")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, e: Exception):
        log.exception("unhandled error")
        _record(500, request.url.path, "Unhandled exception", f"{type(e).__name__}: {e}")
        return error_response(500, "Something went wrong", "An unexpected problem happened on the server.",
                              "Please try again. If it keeps happening, let your administrator know.",
                              f"{type(e).__name__}: {e}. See `docker compose logs backend`.")
