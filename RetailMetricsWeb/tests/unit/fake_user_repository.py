from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.models import AppUser, Role
from repositories.user_repository import DuplicateUserIdentity


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[int, AppUser] = {}
        self.reset_hashes: dict[str, int] = {}
        self.next_id = 1

    def _save(self, user: AppUser) -> AppUser:
        self.users[user.app_user_id] = user
        return user

    def create_analyst(self, username: str, email: str, password_hash: str) -> AppUser:
        if any(
            user.username.lower() == username.lower()
            or user.email.lower() == email.lower()
            for user in self.users.values()
        ):
            raise DuplicateUserIdentity("Username or email is already registered")
        now = datetime.now(timezone.utc)
        user = AppUser(
            app_user_id=self.next_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=Role.ANALYST,
            is_active=True,
            failed_login_attempts=0,
            locked_until=None,
            last_login_at=None,
            password_changed_at=now,
            token_version=1,
            row_version=1,
            created_at=now,
            updated_at=now,
        )
        self.next_id += 1
        return self._save(user)

    def get_by_id(self, app_user_id: int) -> AppUser | None:
        return self.users.get(app_user_id)

    def get_by_login(self, identifier: str) -> AppUser | None:
        normalized = identifier.lower()
        return next(
            (
                user
                for user in self.users.values()
                if user.username.lower() == normalized
                or user.email.lower() == normalized
            ),
            None,
        )

    def get_by_email(self, email: str) -> AppUser | None:
        normalized = email.lower()
        return next(
            (user for user in self.users.values() if user.email.lower() == normalized),
            None,
        )

    def record_failed_login(
        self,
        app_user_id: int,
        limit: int,
        lock_seconds: int,
    ) -> AppUser:
        user = self.users[app_user_id]
        now = datetime.now(timezone.utc)
        attempts = 0 if user.locked_until and user.locked_until <= now else user.failed_login_attempts
        attempts += 1
        locked_until = now + timedelta(seconds=lock_seconds) if attempts >= limit else None
        return self._save(
            replace(
                user,
                failed_login_attempts=attempts,
                locked_until=locked_until,
                row_version=user.row_version + 1,
                updated_at=now,
            )
        )

    def record_successful_login(
        self,
        app_user_id: int,
        replacement_hash: str | None,
    ) -> AppUser:
        user = self.users[app_user_id]
        now = datetime.now(timezone.utc)
        return self._save(
            replace(
                user,
                password_hash=replacement_hash or user.password_hash,
                failed_login_attempts=0,
                locked_until=None,
                last_login_at=now,
                row_version=user.row_version + 1,
                updated_at=now,
            )
        )

    def increment_token_version(self, app_user_id: int) -> AppUser:
        user = self.users[app_user_id]
        return self._save(
            replace(
                user,
                token_version=user.token_version + 1,
                row_version=user.row_version + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )

    def change_password(self, app_user_id: int, password_hash: str) -> AppUser:
        user = self.users[app_user_id]
        now = datetime.now(timezone.utc)
        return self._save(
            replace(
                user,
                password_hash=password_hash,
                password_changed_at=now,
                failed_login_attempts=0,
                locked_until=None,
                token_version=user.token_version + 1,
                row_version=user.row_version + 1,
                updated_at=now,
            )
        )

    def store_reset_token(
        self,
        app_user_id: int,
        token_hash: str,
        lifetime_seconds: int,
    ) -> None:
        del lifetime_seconds
        self.reset_hashes[token_hash] = app_user_id

    def reset_password(self, token_hash: str, password_hash: str) -> AppUser | None:
        app_user_id = self.reset_hashes.pop(token_hash, None)
        if app_user_id is None:
            return None
        user = self.users[app_user_id]
        if not user.is_active:
            return None
        return self.change_password(app_user_id, password_hash)

    def set_role(self, app_user_id: int, role: Role) -> None:
        self._save(replace(self.users[app_user_id], role=role))

    def set_active(self, app_user_id: int, active: bool) -> None:
        self._save(replace(self.users[app_user_id], is_active=active))
