# Vercel entrypoint. The real application lives in server/ so that it stays a
# normal importable package (and so Vercel does not turn every module into its
# own serverless function).
from server.main import app  # noqa: F401
