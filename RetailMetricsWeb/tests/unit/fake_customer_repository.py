from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.models import CustomerAccount, CustomerIdentity, CustomerProfile
from repositories.customer_repository import DuplicateCustomerEmail


class FakeCustomerRepository:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.accounts: dict[int, CustomerAccount] = {}
        self.profiles: dict[int, CustomerProfile] = {}
        self.next_id = 1
        self.now = now

    def create_with_profile(self, email, password_hash, first_name, last_name, phone):
        if any(value.email.lower() == email.lower() for value in self.accounts.values()):
            raise DuplicateCustomerEmail("A customer account already uses that email.")
        account_id = self.next_id
        self.next_id += 1
        account = CustomerAccount(
            account_id, None, email, password_hash, True, 0, None, None, self.now,
            None, None, 1, 1, self.now, self.now,
        )
        profile = CustomerProfile(account_id, first_name, last_name, phone, 1, self.now, self.now)
        self.accounts[account_id] = account
        self.profiles[account_id] = profile
        return CustomerIdentity(account, profile)

    def get_by_id(self, customer_account_id):
        return self.accounts.get(customer_account_id)

    def get_by_email(self, email):
        return next((value for value in self.accounts.values() if value.email.lower() == email.lower()), None)

    def get_profile(self, customer_account_id):
        return self.profiles.get(customer_account_id)

    def get_identity(self, customer_account_id):
        account = self.get_by_id(customer_account_id)
        profile = self.get_profile(customer_account_id)
        return CustomerIdentity(account, profile) if account and profile else None

    def record_failed_login(self, customer_account_id, limit, lock_seconds):
        account = self.accounts[customer_account_id]
        attempts = 1 if account.locked_until and account.locked_until <= self.now else account.failed_login_attempts + 1
        locked_until = self.now + timedelta(seconds=lock_seconds) if attempts >= limit else None
        account = replace(account, failed_login_attempts=attempts, locked_until=locked_until, row_version=account.row_version + 1)
        self.accounts[customer_account_id] = account
        return account

    def record_successful_login(self, customer_account_id, replacement_hash):
        account = self.accounts[customer_account_id]
        account = replace(account, failed_login_attempts=0, locked_until=None, last_login_at=self.now, password_hash=replacement_hash or account.password_hash, row_version=account.row_version + 1)
        self.accounts[customer_account_id] = account
        return account

    def increment_token_version(self, customer_account_id):
        account = self.accounts[customer_account_id]
        account = replace(account, token_version=account.token_version + 1, row_version=account.row_version + 1)
        self.accounts[customer_account_id] = account
        return account

    def change_password(self, customer_account_id, password_hash):
        account = self.accounts[customer_account_id]
        account = replace(account, password_hash=password_hash, token_version=account.token_version + 1, row_version=account.row_version + 1)
        self.accounts[customer_account_id] = account
        return account

    def store_reset_token(self, customer_account_id, token_hash, lifetime_seconds):
        account = self.accounts[customer_account_id]
        self.accounts[customer_account_id] = replace(account, password_reset_token_hash=token_hash, password_reset_expires_at=self.now + timedelta(seconds=lifetime_seconds))

    def reset_password(self, token_hash, password_hash):
        account = next((value for value in self.accounts.values() if value.password_reset_token_hash == token_hash), None)
        if not account:
            return None
        return self.change_password(account.customer_account_id, password_hash)

    def update_profile(self, customer_account_id, first_name, last_name, phone, row_version):
        profile = self.profiles[customer_account_id]
        if profile.row_version != row_version:
            return None
        profile = replace(profile, first_name=first_name, last_name=last_name, phone=phone, row_version=row_version + 1)
        self.profiles[customer_account_id] = profile
        return profile

    def list_identities(self, search, is_active, limit, offset):
        values = [self.get_identity(key) for key in sorted(self.accounts, reverse=True)]
        values = [value for value in values if value is not None]
        return values[offset:offset + limit], len(values)

    def update_active(self, customer_account_id, is_active, row_version):
        account = self.accounts.get(customer_account_id)
        if not account or account.row_version != row_version:
            return None
        account = replace(account, is_active=is_active, token_version=account.token_version + 1, row_version=row_version + 1)
        self.accounts[customer_account_id] = account
        return account

    def unlock(self, customer_account_id, row_version):
        account = self.accounts.get(customer_account_id)
        if not account or account.row_version != row_version:
            return None
        account = replace(account, failed_login_attempts=0, locked_until=None, row_version=row_version + 1)
        self.accounts[customer_account_id] = account
        return account
