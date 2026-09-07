import os


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


class Settings:
    """Read once at import. A missing variable should fail the deploy, not the
    first request that happens to need it."""

    def __init__(self) -> None:
        self.database_url = _require("DATABASE_URL")
        self.supabase_url = _require("SUPABASE_URL").rstrip("/")
        # Legacy Supabase projects sign with a shared HS256 secret; newer ones use
        # asymmetric keys served from JWKS. Support both, prefer JWKS.
        self.supabase_jwt_secret = os.environ.get("SUPABASE_JWT_SECRET") or None
        self.jwt_audience = os.environ.get("SUPABASE_JWT_AUD", "authenticated")
        self.event_slug = os.environ.get("EVENT_SLUG", "tech-arena-2026")
        self.db_pool_max = int(os.environ.get("DB_POOL_MAX", "2"))


settings = Settings()
