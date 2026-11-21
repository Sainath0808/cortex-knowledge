"""Auth endpoints: register, login, refresh, me."""
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.core.exceptions import AuthError, PermissionDenied
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.db.repositories.users import UserRepository
from app.schemas.api import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, db: DB):
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email):
        raise PermissionDenied("Email already registered")
    user = await repo.create(email=payload.email, hashed_password=hash_password(payload.password))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DB):
    user = await UserRepository(db).get_by_email(payload.email)
    # Constant-shape flow: same error whether the email or password is wrong.
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise AuthError("Invalid credentials")
    return TokenResponse(
        access_token=create_token(user.id, user.role.value, "access"),
        refresh_token=create_token(user.id, user.role.value, "refresh"),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DB):
    claims = decode_token(payload.refresh_token, expected_type="refresh")
    user = await UserRepository(db).get(UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive")
    return TokenResponse(
        access_token=create_token(user.id, user.role.value, "access"),
        refresh_token=create_token(user.id, user.role.value, "refresh"),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
