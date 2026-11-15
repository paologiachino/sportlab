"""Database engine and sessions for the application role (DATABASE_URL)."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# The engine holds the connection pool and is shared by the whole process.
# create_engine() does not connect: the first connection opens on first use.
engine = create_engine(
    get_settings().database_url.unicode_string(),
    # Checks a pooled connection before handing it out, so a database restart
    # does not surface as an error on the next request.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed at the end.

    Tests replace it with `app.dependency_overrides[get_db]`.
    """
    with SessionLocal() as session:
        yield session
