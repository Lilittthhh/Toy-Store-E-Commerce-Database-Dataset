from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, status

from core.config import Settings
from core.models import AppUser
from core.security import (
    DUMMY_PASSWORD_HASH,
    InvalidAuthenticationToken,
    create_access_token,
    decode_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    password_hash_needs_upgrade,
    verify_password,
)
from repositories.user_repository import DuplicateUserIdentity, UserRepository
from services.notifications.password_reset import password_reset_message, reset_token_may_be_exposed
from services.notifications.providers import Message


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username/email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings,
                 notification_sink: Callable[[Message], None] | None = None):
        self.repository = repository
        self.settings = settings
        self.notification_sink = notification_sink

    def register(self, username: str, email: str, password: str) -> AppUser:
        try:
            return self.repository.create_analyst(
                username=username.strip().lower(),
                email=email.strip().lower(),
                password_hash=hash_password(password),
            )
        except DuplicateUserIdentity as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def login(self, identifier: str, password: str) -> tuple[str, int]:
        user = self.repository.get_by_login(identifier.strip())
        if user is None:
            verify_password(password, DUMMY_PASSWORD_HASH)
            raise _invalid_credentials()
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is inactive.")
        if user.is_locked():
            raise HTTPException(
                status_code=423,
                detail=f"Account is temporarily locked until {user.locked_until.isoformat()}.",
            )
        if not verify_password(password, user.password_hash):
            failed_user = self.repository.record_failed_login(
                user.app_user_id,
                self.settings.auth_lockout_attempts,
                self.settings.auth_lockout_minutes * 60,
            )
            if failed_user.is_locked():
                raise HTTPException(
                    status_code=423,
                    detail=(
                        "Account is temporarily locked after repeated failed "
                        "login attempts."
                    ),
                )
            raise _invalid_credentials()

        replacement_hash = None
        if password_hash_needs_upgrade(user.password_hash):
            replacement_hash = hash_password(password)
        user = self.repository.record_successful_login(
            user.app_user_id,
            replacement_hash,
        )
        return create_access_token(user, self.settings)

    def authenticate_token(self, token: str) -> AppUser:
        try:
            claims = decode_access_token(token, self.settings)
        except InvalidAuthenticationToken as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        user = self.repository.get_by_id(claims.app_user_id)
        if user is None or user.token_version != claims.token_version:
            raise HTTPException(
                status_code=401,
                detail="Authentication token has been invalidated.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is inactive.")
        if user.is_locked():
            raise HTTPException(status_code=423, detail="Account is temporarily locked.")
        return user

    def logout(self, user: AppUser) -> None:
        self.repository.increment_token_version(user.app_user_id)

    def change_password(
        self,
        user: AppUser,
        current_password: str,
        new_password: str,
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        if verify_password(new_password, user.password_hash):
            raise HTTPException(
                status_code=400,
                detail="New password must differ from the current password.",
            )
        self.repository.change_password(user.app_user_id, hash_password(new_password))

    def forgot_password(self, email: str) -> str | None:
        user = self.repository.get_by_email(email.strip().lower())
        if user is None or not user.is_active:
            return None
        raw_token, token_hash = generate_reset_token()
        self.repository.store_reset_token(
            user.app_user_id,
            token_hash,
            self.settings.auth_reset_token_minutes * 60,
        )
        if self.notification_sink:
            self.notification_sink(password_reset_message(
                user.email, raw_token, self.settings.auth_reset_token_minutes, "staff"
            ))
        return raw_token if reset_token_may_be_exposed(self.settings) else None

    def reset_password(self, reset_token: str, new_password: str) -> None:
        token_hash = hash_reset_token(reset_token)
        user = self.repository.reset_password(token_hash, hash_password(new_password))
        if user is None:
            raise HTTPException(status_code=400, detail="Reset token is invalid or expired.")
