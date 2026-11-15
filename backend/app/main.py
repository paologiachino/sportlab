"""sportlab FastAPI application."""

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings

# Validated at import, so the server refuses to start with a broken environment
# instead of failing later on the first request that needs a missing value.
settings = get_settings()

app = FastAPI(title="sportlab")

app.include_router(health.router, prefix="/api")
