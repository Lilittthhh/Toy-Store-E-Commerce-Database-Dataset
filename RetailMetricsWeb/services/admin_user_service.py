from __future__ import annotations

from fastapi import HTTPException

from core.models import AppUser, Role
from core.security import hash_password
from repositories.user_repository import DuplicateUserIdentity, UserRepository


class AdminUserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def create_user(self, username: str, email: str, password: str, role: Role) -> AppUser:
        try:
            return self.repository.create_user(
                username.strip().lower(),
                email.strip().lower(),
                hash_password(password),
                role,
            )
        except DuplicateUserIdentity as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def get_user(self, app_user_id: int) -> AppUser:
        user = self.repository.get_by_id(app_user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Application user not found.")
        return user

    def change_role(
        self,
        actor: AppUser,
        target_id: int,
        role: Role,
        row_version: int,
    ) -> AppUser:
        target = self._require_version(target_id, row_version)
        if actor.app_user_id == target_id:
            raise HTTPException(status_code=409, detail="Administrators cannot change their own role.")
        if target.role == Role.ADMIN and target.is_active and role != Role.ADMIN:
            self._protect_last_active_admin()
        updated = self.repository.update_role(target_id, role, row_version)
        if updated is None:
            self._raise_stale(target_id, row_version)
        return updated

    def change_active(
        self,
        actor: AppUser,
        target_id: int,
        is_active: bool,
        row_version: int,
    ) -> AppUser:
        target = self._require_version(target_id, row_version)
        if actor.app_user_id == target_id and not is_active:
            raise HTTPException(status_code=409, detail="Administrators cannot deactivate their own account.")
        if target.role == Role.ADMIN and target.is_active and not is_active:
            self._protect_last_active_admin()
        updated = self.repository.update_active(target_id, is_active, row_version)
        if updated is None:
            self._raise_stale(target_id, row_version)
        return updated

    def unlock(self, target_id: int, row_version: int) -> AppUser:
        self._require_version(target_id, row_version)
        updated = self.repository.unlock(target_id, row_version)
        if updated is None:
            self._raise_stale(target_id, row_version)
        return updated

    def _require_version(self, target_id: int, expected: int) -> AppUser:
        target = self.get_user(target_id)
        if target.row_version != expected:
            raise HTTPException(
                status_code=409,
                detail=f"Stale row_version: expected {expected}, current value is {target.row_version}.",
            )
        return target

    def _protect_last_active_admin(self) -> None:
        if self.repository.count_active_admins_locked() <= 1:
            raise HTTPException(status_code=409, detail="The last active Admin cannot be removed.")

    def _raise_stale(self, target_id: int, expected: int) -> None:
        current = self.get_user(target_id)
        raise HTTPException(
            status_code=409,
            detail=f"Stale row_version: expected {expected}, current value is {current.row_version}.",
        )
