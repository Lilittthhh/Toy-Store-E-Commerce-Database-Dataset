from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from core.config import Settings
from core.models import AppUser, CustomerAccount


PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("Dummy-password-only-for-timing-1!")


class InvalidAuthenticationToken(ValueError):
    pass


@dataclass(frozen=True)
class TokenClaims:
    app_user_id: int
    token_version: int


@dataclass(frozen=True)
class CustomerTokenClaims:
    customer_account_id: int
    token_version: int


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bool(PASSWORD_HASHER.verify(password_hash, password))
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_hash_needs_upgrade(password_hash: str) -> bool:
    try:
        return PASSWORD_HASHER.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_access_token(user: AppUser, settings: Settings) -> tuple[str, int]:
    issued_at = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=settings.jwt_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(user.app_user_id),
        "ver": user.token_version,
        "type": "access",
        "jti": secrets.token_hex(16),
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "ver", "type", "jti", "iat", "exp"]},
        )
        if payload.get("type") != "access":
            raise InvalidAuthenticationToken("Unexpected token type")
        return TokenClaims(
            app_user_id=int(payload["sub"]),
            token_version=int(payload["ver"]),
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAuthenticationToken("Invalid or expired authentication token") from exc


def create_customer_access_token(
    customer: CustomerAccount,
    settings: Settings,
) -> tuple[str, int]:
    issued_at = datetime.now(timezone.utc)
    lifetime = timedelta(minutes=settings.jwt_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(customer.customer_account_id),
        "ver": customer.token_version,
        "type": "customer_access",
        "jti": secrets.token_hex(16),
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, int(lifetime.total_seconds())


def decode_customer_access_token(
    token: str,
    settings: Settings,
) -> CustomerTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "ver", "type", "jti", "iat", "exp"]},
        )
        if payload.get("type") != "customer_access":
            raise InvalidAuthenticationToken("Unexpected token type")
        return CustomerTokenClaims(
            customer_account_id=int(payload["sub"]),
            token_version=int(payload["ver"]),
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise InvalidAuthenticationToken("Invalid or expired authentication token") from exc


def generate_reset_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_reset_token(raw_token)


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
