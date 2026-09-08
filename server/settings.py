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
        # Legacy Supabase projects sign with a shared HS256 secret; newer ones
        # use asymmetric keys served from JWKS. JWKS is the default and the
        # symmetric path must be opted into explicitly: a shared secret that
        # leaks lets anyone mint a token for any user, and a stray value copied
        # from a .env into a deployment would do exactly that silently.
        self.allow_hs256 = os.environ.get("ALLOW_HS256_JWT", "").lower() in ("1", "true", "yes")
        self.supabase_jwt_secret = (
            os.environ.get("SUPABASE_JWT_SECRET") if self.allow_hs256 else None
        )
        if self.allow_hs256 and os.environ.get("VERCEL_ENV") == "production":
            raise RuntimeError(
                "ALLOW_HS256_JWT must not be set in production — use asymmetric JWKS keys"
            )
        self.jwt_audience = os.environ.get("SUPABASE_JWT_AUD", "authenticated")
        self.event_slug = os.environ.get("EVENT_SLUG", "tech-arena-2026")
        self.db_pool_max = int(os.environ.get("DB_POOL_MAX", "2"))
        self.cron_secret = os.environ.get("CRON_SECRET") or None


settings = Settings()
