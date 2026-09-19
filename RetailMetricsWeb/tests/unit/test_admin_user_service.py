from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from core.models import AppUser, Role
from services.admin_user_service import AdminUserService


def make_user(user_id: int, role: Role, *, active: bool = True, version: int = 1) -> AppUser:
    now = datetime.now(timezone.utc)
    return AppUser(user_id, f"user{user_id}", f"user{user_id}@example.com", "hash", role, active, 0, None, None, now, 1, version, now, now)


class FakeRepository:
    def __init__(self, users: list[AppUser]):
        self.users = {user.app_user_id: user for user in users}

    def get_by_id(self, user_id):
        return self.users.get(user_id)

    def count_active_admins_locked(self):
        return sum(user.role == Role.ADMIN and user.is_active for user in self.users.values())

    def update_role(self, user_id, role, version):
        user = self.users[user_id]
        if user.row_version != version:
            return None
        updated = replace(user, role=role, row_version=version + 1, token_version=user.token_version + 1)
        self.users[user_id] = updated
        return updated

    def update_active(self, user_id, active, version):
        user = self.users[user_id]
        if user.row_version != version:
            return None
        updated = replace(user, is_active=active, row_version=version + 1, token_version=user.token_version + 1)
        self.users[user_id] = updated
        return updated

    def unlock(self, user_id, version):
        user = self.users[user_id]
        return replace(user, failed_login_attempts=0, locked_until=None, row_version=version + 1)


def test_admin_cannot_demote_or_deactivate_self() -> None:
    actor = make_user(1, Role.ADMIN)
    service = AdminUserService(FakeRepository([actor]))
    with pytest.raises(HTTPException, match="own role"):
        service.change_role(actor, 1, Role.ANALYST, 1)
    with pytest.raises(HTTPException, match="own account"):
        service.change_active(actor, 1, False, 1)


def test_last_active_admin_is_protected() -> None:
    actor = make_user(1, Role.ADMIN)
    target = make_user(2, Role.ADMIN)
    repository = FakeRepository([replace(actor, is_active=False), target])
    service = AdminUserService(repository)
    with pytest.raises(HTTPException, match="last active Admin"):
        service.change_role(actor, 2, Role.ANALYST, 1)


def test_role_change_increments_version_and_invalidates_tokens() -> None:
    actor = make_user(1, Role.ADMIN)
    target = make_user(2, Role.ANALYST)
    service = AdminUserService(FakeRepository([actor, target]))
    updated = service.change_role(actor, 2, Role.OPERATIONS_STAFF, 1)
    assert updated.role == Role.OPERATIONS_STAFF
    assert updated.row_version == 2
    assert updated.token_version == 2
