"""SQLAlchemy models.

Importing this package registers every model on `Base.metadata`, which Alembic
compares with the database: import `Base` from here, not from app.db.base,
wherever the full set of tables matters (migrations, their tests).
"""

from app.db.base import Base
from app.models.user import User, UserRole, UserStatus

__all__ = ["Base", "User", "UserRole", "UserStatus"]
