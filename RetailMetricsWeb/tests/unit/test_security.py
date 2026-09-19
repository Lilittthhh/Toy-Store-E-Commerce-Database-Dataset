from core.config import Settings
from core.models import AppUser, CustomerAccount, Role
from core.security import (
    InvalidAuthenticationToken,
    create_access_token,
    create_customer_access_token,
    decode_customer_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

from datetime import datetime, timezone

import pytest


def test_password_hash_is_argon2id_and_verifies() -> None:
    encoded = hash_password("Strong-password-1!")
    assert encoded.startswith("$argon2id$")
    assert "Strong-password-1!" not in encoded
    assert verify_password("Strong-password-1!", encoded)
    assert not verify_password("incorrect", encoded)


def test_signed_token_rejects_tampering() -> None:
    now = datetime.now(timezone.utc)
    user = AppUser(
        app_user_id=1,
        username="analyst",
        email="analyst@example.com",
        password_hash="not-returned",
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
    settings = Settings(jwt_secret_key="s" * 64)
    token, _ = create_access_token(user, settings)
    claims = decode_access_token(token, settings)
    assert claims.app_user_id == 1
    assert claims.token_version == 1

    header, payload, signature = token.split(".")
    tampered_signature = ("a" if signature[0] != "a" else "b") + signature[1:]
    with pytest.raises(InvalidAuthenticationToken):
        decode_access_token(f"{header}.{payload}.{tampered_signature}", settings)


def test_staff_and_customer_tokens_are_not_interchangeable() -> None:
    now = datetime.now(timezone.utc)
    customer = CustomerAccount(
        1, None, "customer@example.com", "hash", True, 0, None, None, now,
        None, None, 1, 1, now, now,
    )
    settings = Settings(jwt_secret_key="s" * 64)
    customer_token, _ = create_customer_access_token(customer, settings)
    assert decode_customer_access_token(customer_token, settings).customer_account_id == 1
    with pytest.raises(InvalidAuthenticationToken):
        decode_access_token(customer_token, settings)

    user = AppUser(1, "staff", "staff@example.com", "hash", Role.ANALYST, True, 0, None, None, now, 1, 1, now, now)
    staff_token, _ = create_access_token(user, settings)
    with pytest.raises(InvalidAuthenticationToken):
        decode_customer_access_token(staff_token, settings)
