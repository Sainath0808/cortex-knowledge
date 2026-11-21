"""FastAPI dependencies: authenticated user resolution and RBAC checks."""
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, PermissionDenied
from app.core.security import decode_token
from app.db.models import User, UserRole
from app.db.repositories.users import UserRepository
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)

DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    if credentials is None:
        raise AuthError("Missing bearer token")
    payload = decode_token(credentials.credentials, expected_type="access")
    user = await UserRepository(db).get(UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDenied(f"Requires one of roles: {[r.value for r in roles]}")
        return user

    return Depends(checker)
