from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, status

from core.config import Settings
from core.models import CustomerAccount, CustomerIdentity, CustomerProfile
from core.security import (
    DUMMY_PASSWORD_HASH,
    InvalidAuthenticationToken,
    create_customer_access_token,
    decode_customer_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    password_hash_needs_upgrade,
    verify_password,
)
from repositories.customer_repository import CustomerRepository, DuplicateCustomerEmail
from services.notifications.password_reset import password_reset_message, reset_token_may_be_exposed
from services.notifications.providers import Message


def _invalid_customer_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class CustomerAuthService:
    def __init__(self, repository: CustomerRepository, settings: Settings,
                 notification_sink: Callable[[Message], None] | None = None):
        self.repository = repository
        self.settings = settings
        self.notification_sink = notification_sink

    def register(self, email: str, password: str, first_name: str, last_name: str, phone: str | None) -> CustomerIdentity:
        try:
            return self.repository.create_with_profile(
                email=email.strip().lower(), password_hash=hash_password(password),
                first_name=first_name, last_name=last_name, phone=phone,
            )
        except DuplicateCustomerEmail as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def login(self, email: str, password: str) -> tuple[str, int]:
        account = self.repository.get_by_email(email.strip().lower())
        if account is None:
            verify_password(password, DUMMY_PASSWORD_HASH)
            raise _invalid_customer_credentials()
        if not account.is_active:
            raise HTTPException(status_code=403, detail="Customer account is inactive.")
        if account.is_locked():
            raise HTTPException(status_code=423, detail="Customer account is temporarily locked.")
        if not verify_password(password, account.password_hash):
            failed = self.repository.record_failed_login(
                account.customer_account_id,
                self.settings.auth_lockout_attempts,
                self.settings.auth_lockout_minutes * 60,
            )
            if failed.is_locked():
                raise HTTPException(status_code=423, detail="Customer account is temporarily locked after repeated failed login attempts.")
            raise _invalid_customer_credentials()
        replacement_hash = hash_password(password) if password_hash_needs_upgrade(account.password_hash) else None
        account = self.repository.record_successful_login(account.customer_account_id, replacement_hash)
        return create_customer_access_token(account, self.settings)

    def authenticate_token(self, token: str) -> CustomerAccount:
        try:
            claims = decode_customer_access_token(token, self.settings)
        except InvalidAuthenticationToken as exc:
            raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
        account = self.repository.get_by_id(claims.customer_account_id)
        if account is None or account.token_version != claims.token_version:
            raise HTTPException(status_code=401, detail="Authentication token has been invalidated.", headers={"WWW-Authenticate": "Bearer"})
        if not account.is_active:
            raise HTTPException(status_code=403, detail="Customer account is inactive.")
        if account.is_locked():
            raise HTTPException(status_code=423, detail="Customer account is temporarily locked.")
        return account

    def identity(self, account: CustomerAccount) -> CustomerIdentity:
        identity = self.repository.get_identity(account.customer_account_id)
        if identity is None:
            raise HTTPException(status_code=404, detail="Customer profile was not found.")
        return identity

    def logout(self, account: CustomerAccount) -> None:
        self.repository.increment_token_version(account.customer_account_id)

    def change_password(self, account: CustomerAccount, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, account.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        if verify_password(new_password, account.password_hash):
            raise HTTPException(status_code=400, detail="New password must differ from the current password.")
        self.repository.change_password(account.customer_account_id, hash_password(new_password))

    def forgot_password(self, email: str) -> str | None:
        account = self.repository.get_by_email(email.strip().lower())
        if account is None or not account.is_active:
            return None
        raw_token, token_hash = generate_reset_token()
        self.repository.store_reset_token(account.customer_account_id, token_hash, self.settings.auth_reset_token_minutes * 60)
        if self.notification_sink:
            self.notification_sink(password_reset_message(
                account.email, raw_token, self.settings.auth_reset_token_minutes, "customer"
            ))
        return raw_token if reset_token_may_be_exposed(self.settings) else None

    def reset_password(self, reset_token: str, new_password: str) -> None:
        account = self.repository.reset_password(hash_reset_token(reset_token), hash_password(new_password))
        if account is None:
            raise HTTPException(status_code=400, detail="Reset token is invalid or expired.")

    def get_profile(self, account: CustomerAccount) -> CustomerProfile:
        profile = self.repository.get_profile(account.customer_account_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Customer profile was not found.")
        return profile

    def update_profile(self, account: CustomerAccount, first_name: str, last_name: str, phone: str | None, row_version: int) -> CustomerProfile:
        current = self.get_profile(account)
        if current.row_version != row_version:
            raise HTTPException(status_code=409, detail=f"Stale row_version: expected {row_version}, current value is {current.row_version}.")
        updated = self.repository.update_profile(account.customer_account_id, first_name, last_name, phone, row_version)
        if updated is None:
            current = self.get_profile(account)
            raise HTTPException(status_code=409, detail=f"Stale row_version: expected {row_version}, current value is {current.row_version}.")
        return updated
