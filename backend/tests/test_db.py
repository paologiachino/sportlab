from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db


def test_database_answers(db_session: Session) -> None:
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1


def test_get_db_closes_the_session(db_session: Session) -> None:
    dependency = get_db()
    session = next(dependency)
    session.execute(text("SELECT 1"))
    assert session.in_transaction()

    # FastAPI resumes the generator after the response: the session closes
    dependency.close()

    assert not session.in_transaction()
