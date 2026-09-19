from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import HTTPException

from core.config import Settings
from core.security import decode_customer_access_token, hash_password
from services.customer_auth_service import CustomerAuthService
from tests.unit.fake_customer_repository import FakeCustomerRepository


PASSWORD = "Customer-password-1!"
NEW_PASSWORD = "Customer-password-2!"


def service_and_identity():
    repository = FakeCustomerRepository()
    service = CustomerAuthService(repository, Settings(jwt_secret_key="s" * 64, auth_lockout_attempts=3))
    identity = repository.create_with_profile("customer@example.com", hash_password(PASSWORD), "Ada", "Lovelace", None)
    return service, repository, identity


def test_customer_login_uses_customer_token_and_invalidates_on_logout() -> None:
    service, repository, identity = service_and_identity()
    token, _ = service.login("CUSTOMER@example.com", PASSWORD)
    claims = decode_customer_access_token(token, service.settings)
    assert claims.customer_account_id == identity.account.customer_account_id
    assert service.authenticate_token(token).email == "customer@example.com"
    service.logout(repository.get_by_id(identity.account.customer_account_id))
    with pytest.raises(HTTPException) as raised:
        service.authenticate_token(token)
    assert raised.value.status_code == 401


def test_customer_wrong_and_missing_email_share_generic_error_and_lockout() -> None:
    service, repository, identity = service_and_identity()
    for email in ("missing@example.com", "customer@example.com"):
        with pytest.raises(HTTPException) as raised:
            service.login(email, "wrong")
        assert raised.value.status_code == 401
        assert raised.value.detail == "Invalid email or password."
    with pytest.raises(HTTPException):
        service.login("customer@example.com", "wrong")
    with pytest.raises(HTTPException) as locked:
        service.login("customer@example.com", "wrong")
    assert locked.value.status_code == 423


def test_profile_update_is_owned_and_versioned() -> None:
    service, repository, identity = service_and_identity()
    updated = service.update_profile(identity.account, "Grace", "Hopper", "555", 1)
    assert updated.first_name == "Grace"
    assert updated.row_version == 2
    with pytest.raises(HTTPException) as stale:
        service.update_profile(identity.account, "Stale", "Name", None, 1)
    assert stale.value.status_code == 409


def test_inactive_and_locked_customers_are_refused() -> None:
    service, repository, identity = service_and_identity()
    account = replace(identity.account, is_active=False)
    repository.accounts[account.customer_account_id] = account
    with pytest.raises(HTTPException) as inactive:
        service.login(account.email, PASSWORD)
    assert inactive.value.status_code == 403
