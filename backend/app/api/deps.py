"""Who is calling: dependencies every endpoint declares.

- CurrentUser: any signed-in user, whatever the status (only /api/auth uses it,
  so a pending user can see that they are waiting for approval).
- ActiveUser: approved users; pending and disabled users get 403.
- AdminUser: active administrators.

Status and role are read from the database on every request, not from the
token, so a disabled or demoted user loses access at their next request.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.cookies import cookie_names
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models import User, UserRole, UserStatus

NOT_SIGNED_IN = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Not signed in", headers={"WWW-Authenticate": "Cookie"}
)


def current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = request.cookies.get(cookie_names(settings).access)
    if not token:
        raise NOT_SIGNED_IN
    try:
        user_id = decode_access_token(token, settings.secret_key.get_secret_value())
    except InvalidTokenError:
        # Expired, forged or malformed: the same answer, the frontend refreshes
        raise NOT_SIGNED_IN from None
    user = db.get(User, user_id)
    if user is None:  # deleted since the token was issued
        raise NOT_SIGNED_IN
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def active_user(user: CurrentUser) -> User:
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Account {user.status}")
    return user


ActiveUser = Annotated[User, Depends(active_user)]


def admin_user(user: ActiveUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrators only")
    return user


AdminUser = Annotated[User, Depends(admin_user)]
