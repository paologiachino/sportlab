"""Health checks: the process (/api/health) and the database (/api/health/db)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    """Liveness check: the process is up and answering requests."""
    return {"status": "ok"}


@router.get("/db")
def health_db(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Readiness check: the database answers a trivial query."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Only the error type: the full message can include host and user names.
        logger.warning("Database health check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from None
    return {"status": "ok"}
