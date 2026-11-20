"""All runtime settings come from environment variables (see .env.example)."""
import os
from dataclasses import dataclass, field


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _rate(value: str) -> tuple[int, int]:
    """'10/3600' -> (10 requests, per 3600 seconds)."""
    count, seconds = value.split("/")
    return int(count), int(seconds)


@dataclass(frozen=True)
class Settings:
    # AI: URL of the ai-service, or "inprocess" to run it inside this process (single-app hosts
    # like PythonAnywhere; see services/inprocess_ai.py and docs/DEPLOY_FREE.md).
    ai_service_url: str = os.getenv("AI_SERVICE_URL", "http://ai-service:8000")
    ai_service_path: str = os.getenv("AI_SERVICE_PATH", "")  # where ai-service/ lives, for "inprocess"
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "180"))

    # Storage: PostgreSQL (e.g. Neon) when DATABASE_URL is set, otherwise a SQLite file at DB_PATH.
    database_url: str = os.getenv("DATABASE_URL", "")
    db_path: str = os.getenv("DB_PATH", "/data/umlforge.db")

    # Only needed when the frontend is served from another origin (GitHub Pages, local dev).
    cors_origins: list[str] = field(default_factory=lambda: _list(os.getenv("CORS_ORIGINS", "")))

    # Published links (no accounts; they simply expire).
    share_max_hours: int = int(os.getenv("SHARE_MAX_HOURS", "168"))       # 7 days
    share_max_bytes: int = int(os.getenv("SHARE_MAX_BYTES", "1000000"))   # 1 MB per diagram

    # Rate limits per client IP, "requests/seconds". Optional Upstash Redis makes them shared across workers.
    limit_publish: tuple[int, int] = _rate(os.getenv("RATE_LIMIT_PUBLISH", "10/3600"))
    limit_view: tuple[int, int] = _rate(os.getenv("RATE_LIMIT_VIEW", "120/60"))
    limit_ai: tuple[int, int] = _rate(os.getenv("RATE_LIMIT_AI", "20/600"))
    # Cap on AI calls from ALL visitors together, so a public demo can't drain a free AI key. "0/..." = off.
    limit_ai_global: tuple[int, int] = _rate(os.getenv("RATE_LIMIT_AI_GLOBAL", "500/86400"))
    upstash_url: str = os.getenv("UPSTASH_REDIS_REST_URL", "")
    upstash_token: str = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

    # Serve the frontend from this backend (single-container hosting). Empty = frontend is hosted elsewhere.
    frontend_dir: str = os.getenv("FRONTEND_DIR", "")

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.db_path}"


settings = Settings()
