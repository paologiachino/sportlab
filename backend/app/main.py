"""sportlab FastAPI application."""

from fastapi import FastAPI

from app.core.config import get_settings

# Validated at import, so the server refuses to start with a broken environment
# instead of failing later on the first request that needs a missing value.
settings = get_settings()

app = FastAPI(title="sportlab")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness check: the process is up and answering requests."""
    return {"status": "ok"}
