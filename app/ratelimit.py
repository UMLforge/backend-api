"""Per-IP rate limiting with fixed time windows.

- MemoryLimiter: default; fine for one process (Docker, PythonAnywhere free = 1 worker).
- UpstashLimiter: when UPSTASH_REDIS_REST_URL/TOKEN are set; shared across processes/servers. Uses Upstash's
  HTTPS REST API (no Redis client needed, works on hosts that only allow HTTPS out).
If Redis can't be reached the request is allowed (fail open) and a warning is logged.
"""
import logging
import time

import httpx
from fastapi import Request

from .config import settings
from .errors import AppError

log = logging.getLogger("umlforge.ratelimit")


class MemoryLimiter:
    def __init__(self):
        self._windows: dict[str, tuple[int, int]] = {}  # key -> (window number, count)

    async def hit(self, key: str, limit: int, window: int) -> int:
        """Counts one request; returns seconds to wait if over the limit, else 0."""
        now = time.time()
        current = int(now // window)
        win, count = self._windows.get(key, (current, 0))
        if win != current:
            win, count = current, 0
        count += 1
        self._windows[key] = (win, count)
        if len(self._windows) > 50_000:  # drop old windows now and then
            self._windows = {k: v for k, v in self._windows.items() if v[0] >= current}
        return int((current + 1) * window - now) + 1 if count > limit else 0


class UpstashLimiter:
    def __init__(self, url: str, token: str):
        self._http = httpx.AsyncClient(base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=3)

    async def hit(self, key: str, limit: int, window: int) -> int:
        bucket = f"rl:{key}:{int(time.time() // window)}"
        try:
            r = await self._http.post("/pipeline", json=[["INCR", bucket], ["EXPIRE", bucket, window]])
            r.raise_for_status()
            count = int(r.json()[0]["result"])
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as e:
            log.warning("rate limiter unavailable, allowing request: %s", e)
            return 0
        return int(window - time.time() % window) + 1 if count > limit else 0


limiter = UpstashLimiter(settings.upstash_url, settings.upstash_token) if settings.upstash_url else MemoryLimiter()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")  # set by nginx / PythonAnywhere / other proxies
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


async def enforce(request: Request, name: str, rule: tuple[int, int], what: str) -> None:
    """Raises a friendly 429 when this client exceeded `rule` (count, seconds) for `name`."""
    limit, window = rule
    wait = await limiter.hit(f"{name}:{client_ip(request)}", limit, window)
    if wait:
        when = f"{wait} seconds" if wait < 90 else f"{round(wait / 60)} minutes"
        raise AppError(429, "Too many requests", f"You've {what} a lot in a short time.", f"Try again in {when}.",
                       details=f"rate limit {name}: {limit} per {window}s for {client_ip(request)}")


async def enforce_global(name: str, rule: tuple[int, int], title: str, message: str) -> None:
    """Same, but one counter for everyone (e.g. the daily AI budget of a demo). A limit of 0 disables it."""
    limit, window = rule
    if limit <= 0:
        return
    wait = await limiter.hit(f"{name}:all", limit, window)
    if wait:
        hours = max(1, round(wait / 3600))
        raise AppError(429, title, message, f"Try again in about {hours} hour{'s' if hours > 1 else ''}.",
                       details=f"global limit {name}: {limit} per {window}s reached")
