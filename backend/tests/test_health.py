from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app

client = TestClient(app)


class UnreachableDatabase:
    """Stands in for a Session whose database is down."""

    def execute(self, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("host=db.internal user=app"))


@pytest.fixture
def override_db() -> Iterator[None]:
    """Removes any dependency override at the end of the test."""
    yield
    app.dependency_overrides.clear()


def test_health_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_returns_ok(db_session: Session, override_db: None) -> None:
    app.dependency_overrides[get_db] = lambda: db_session

    response = client.get("/api/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_unavailable(override_db: None, caplog: pytest.LogCaptureFixture) -> None:
    app.dependency_overrides[get_db] = UnreachableDatabase

    response = client.get("/api/health/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    # Connection details stay out of both the response and the logs
    assert "db.internal" not in response.text
    assert "db.internal" not in caplog.text
    assert "OperationalError" in caplog.text
