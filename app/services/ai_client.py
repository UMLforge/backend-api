"""HTTP client for the separate ai-service. The backend never talks to a model directly."""
import httpx

# User-facing wording shared by every "AI can't be reached" case. Developer specifics go in `details`.
UNAVAILABLE_TITLE = "AI service is down"
UNAVAILABLE_MESSAGE = "The AI service isn't responding right now."
UNAVAILABLE_HINT = "Drawing, analysis and saving still work. Try the AI again later."


class AIUnavailable(Exception):
    """AI could not answer. title/message/hint are for end users; details are for admins."""

    def __init__(self, title: str, message: str = "", hint: str = "", details: str = ""):
        super().__init__(details or message or title)
        self.title, self.message, self.hint, self.details = title, message, hint, details

    def public(self) -> dict:
        return {"title": self.title, "message": self.message, "hint": self.hint, "details": self.details}


def service_down(reason: str) -> AIUnavailable:
    return AIUnavailable(UNAVAILABLE_TITLE, UNAVAILABLE_MESSAGE, UNAVAILABLE_HINT,
                         f"backend could not reach ai-service ({reason}). Check `docker compose ps` and "
                         "`docker compose logs ai-service`.")


class AIClient:
    def __init__(self, base_url: str, timeout: float, ai_service_path: str = ""):
        transport = None
        if base_url == "inprocess":  # ai-service runs in this process (single-app hosting)
            from .inprocess_ai import load_ai_app
            transport, base_url = httpx.ASGITransport(app=load_ai_app(ai_service_path)), "http://ai-service"
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=httpx.Timeout(timeout, connect=5))

    async def close(self) -> None:
        await self._http.aclose()

    async def status(self) -> dict:
        try:
            r = await self._http.get("/health", timeout=5)
            r.raise_for_status()
            return {"available": True, **r.json()}
        except httpx.HTTPError as e:
            return {"available": False, **service_down(type(e).__name__).public()}

    async def _post(self, path: str, payload: dict) -> dict:
        try:
            r = await self._http.post(path, json=payload)
        except httpx.TimeoutException as e:
            raise AIUnavailable("The AI is taking too long", "The AI model is busy or still starting up.",
                                "Wait a moment and try again.",
                                f"no answer from ai-service before the timeout ({type(e).__name__}). "
                                "Raise AI_TIMEOUT_SECONDS or use a smaller/faster model.") from e
        except httpx.HTTPError as e:
            raise service_down(type(e).__name__) from e
        if r.status_code >= 400:
            try:
                err = r.json()["error"]
            except (ValueError, KeyError, TypeError):
                raise AIUnavailable(UNAVAILABLE_TITLE, UNAVAILABLE_MESSAGE, UNAVAILABLE_HINT,
                                    f"ai-service returned HTTP {r.status_code} without an error body") from None
            raise AIUnavailable(err.get("title") or UNAVAILABLE_TITLE, err.get("message", ""), err.get("hint", ""),
                                err.get("details", ""))
        return r.json()

    async def starter(self, problem: str) -> dict:
        return await self._post("/v1/starter", {"problem": problem})

    async def review(self, payload: dict) -> dict:
        return await self._post("/v1/review", payload)
