"""Email + password authentication (Argon2 hashing, JWT bearer tokens)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import EmailStr, Field
from sqlalchemy import Boolean, Column, DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from credlayer.api.deps import get_db_session
from credlayer.api.envelope import Envelope, ok
from credlayer.core.config import get_settings
from credlayer.db.base import Base
from credlayer.schemas.common import CamelModel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

ROLE_USER = "user"
ROLE_ADMIN = "admin"
RESET_TOKEN_TTL = timedelta(hours=1)


class UserDB(Base):
    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, server_default="user")
    display_name = Column(String(256), nullable=True)
    wallet_address = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    token_version = Column(Integer, nullable=False, server_default="0")
    reset_token_hash = Column(String(128), nullable=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")


class User(CamelModel):
    id: UUID
    email: str
    role: str
    display_name: str | None = None
    wallet_address: str | None = None
    created_at: datetime


class RegisterRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=256)
    wallet_address: str | None = Field(default=None, max_length=64)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class TokenResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class ForgotPasswordRequest(CamelModel):
    email: EmailStr


class ResetPasswordRequest(CamelModel):
    token: str
    new_password: str = Field(min_length=8, max_length=256)


class Message(CamelModel):
    detail: str


def _issue_token(user: UserDB) -> TokenResponse:
    s = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=s.jwt_expire_minutes)
    token = jwt.encode(
        {"sub": str(user.id), "ver": user.token_version, "role": user.role, "iat": now, "exp": exp},
        s.jwt_secret,
        algorithm="HS256",
    )
    return TokenResponse(
        access_token=token,
        expires_in=s.jwt_expire_minutes * 60,
        user=User.model_validate(user, from_attributes=True),
    )


def _hash_reset(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db_session),
) -> UserDB:
    """Dependency for protected routes."""
    if creds is None:
        raise _unauthorized()
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("Invalid or expired token")
    user = await db.get(UserDB, user_id)
    if user is None or not user.is_active or user.token_version != payload.get("ver"):
        raise _unauthorized("Invalid or expired token")
    return user


def require_roles(*roles: str):
    """Dependency factory: `Depends(require_roles("admin"))`."""

    async def _dep(user: UserDB = Depends(get_current_user)) -> UserDB:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return _dep


@router.post("/register", response_model=Envelope[TokenResponse], status_code=201)
async def register(
    body: RegisterRequest, db: AsyncSession = Depends(get_db_session)
) -> Envelope[TokenResponse]:
    email = body.email.lower()
    if (await db.execute(select(UserDB).where(UserDB.email == email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = UserDB(
        email=email,
        password_hash=_hasher.hash(body.password),
        role=ROLE_ADMIN if email in get_settings().admin_emails else ROLE_USER,
        display_name=body.display_name,
        wallet_address=body.wallet_address,
        token_version=0,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ok(_issue_token(user))


@router.post("/login", response_model=Envelope[TokenResponse])
async def login(
    body: LoginRequest, db: AsyncSession = Depends(get_db_session)
) -> Envelope[TokenResponse]:
    user = (
        await db.execute(select(UserDB).where(UserDB.email == body.email.lower()))
    ).scalar_one_or_none()
    try:
        if user is None:
            _hasher.verify(_DUMMY_HASH, body.password)  # equalize timing
            raise VerifyMismatchError()
        _hasher.verify(user.password_hash, body.password)
    except (VerifyMismatchError, InvalidHashError):
        raise _unauthorized("Invalid email or password")
    if not user.is_active:
        raise _unauthorized("Invalid email or password")
    return ok(_issue_token(user))


_DUMMY_HASH = _hasher.hash("credlayer-dummy-password")


@router.post("/logout", response_model=Envelope[Message])
async def logout(
    user: UserDB = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)
) -> Envelope[Message]:
    """Revokes every token issued to this user (bumps token_version)."""
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return ok(Message(detail="Logged out"))


@router.get("/me", response_model=Envelope[User])
async def me(user: UserDB = Depends(get_current_user)) -> Envelope[User]:
    return ok(User.model_validate(user, from_attributes=True))


@router.post("/forgot-password", response_model=Envelope[Message])
async def forgot_password(
    body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db_session)
) -> Envelope[Message]:
    """Always responds the same, so it does not reveal which emails exist."""
    user = (
        await db.execute(select(UserDB).where(UserDB.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = _hash_reset(token)
        user.reset_token_expires_at = datetime.now(UTC) + RESET_TOKEN_TTL
        await db.commit()
        # No email provider is wired up yet. Outside production the token is logged
        # so the flow can be exercised; in production, deliver it by email here.
        if get_settings().environment != "production":
            logger.info("password_reset_token", email=user.email, token=token)
    return ok(Message(detail="If the account exists, a reset link has been sent"))


@router.post("/reset-password", response_model=Envelope[Message])
async def reset_password(
    body: ResetPasswordRequest, db: AsyncSession = Depends(get_db_session)
) -> Envelope[Message]:
    user = (
        await db.execute(
            select(UserDB).where(UserDB.reset_token_hash == _hash_reset(body.token))
        )
    ).scalar_one_or_none()
    if (
        user is None
        or user.reset_token_expires_at is None
        or user.reset_token_expires_at < datetime.now(UTC)
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")
    user.password_hash = _hasher.hash(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return ok(Message(detail="Password updated"))


@router.get("/admin/users", response_model=Envelope[list[User]])
async def list_users(
    _: UserDB = Depends(require_roles(ROLE_ADMIN)), db: AsyncSession = Depends(get_db_session)
) -> Envelope[list[User]]:
    rows = (await db.execute(select(UserDB).order_by(UserDB.created_at.desc()))).scalars().all()
    return ok([User.model_validate(r, from_attributes=True) for r in rows])
