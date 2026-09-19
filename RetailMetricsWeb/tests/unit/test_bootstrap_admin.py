from __future__ import annotations

import pytest

from scripts import bootstrap_admin


PASSWORD = "Bootstrap-password-1!"


class FakeCursor:
    def __init__(self, *, active_admin: bool = False, duplicate=None):
        self.active_admin = active_admin
        self.duplicate = duplicate
        self.result = None
        self.calls: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query: str, parameters: tuple | None = None) -> None:
        normalized = " ".join(query.split())
        self.calls.append((normalized, parameters))
        if "SELECT EXISTS" in normalized:
            self.result = (self.active_admin,)
        elif "SELECT username, email" in normalized:
            self.result = self.duplicate
        elif "INSERT INTO public.app_users" in normalized:
            self.result = (42,)

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.fake_cursor


def test_bootstrap_refuses_when_active_admin_exists(monkeypatch) -> None:
    cursor = FakeCursor(active_admin=True)
    monkeypatch.setattr(bootstrap_admin, "hash_password", lambda _: "argon2id-hash")

    with pytest.raises(bootstrap_admin.BootstrapRefused, match="active Admin"):
        bootstrap_admin.create_initial_admin(
            FakeConnection(cursor),
            "initial_admin",
            "admin@example.com",
            PASSWORD,
        )

    assert not any("INSERT INTO" in query for query, _ in cursor.calls)


def test_bootstrap_refuses_duplicate_identity(monkeypatch) -> None:
    cursor = FakeCursor(duplicate=("existing", "existing@example.com"))
    monkeypatch.setattr(bootstrap_admin, "hash_password", lambda _: "argon2id-hash")

    with pytest.raises(bootstrap_admin.BootstrapRefused, match="already registered"):
        bootstrap_admin.create_initial_admin(
            FakeConnection(cursor),
            "initial_admin",
            "admin@example.com",
            PASSWORD,
        )

    assert not any("INSERT INTO" in query for query, _ in cursor.calls)


def test_bootstrap_inserts_only_hash_and_admin_role(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(bootstrap_admin, "hash_password", lambda _: "argon2id-hash")

    app_user_id = bootstrap_admin.create_initial_admin(
        FakeConnection(cursor),
        "Initial_Admin",
        "Admin@Example.com",
        PASSWORD,
    )

    assert app_user_id == 42
    insert_call = next(call for call in cursor.calls if "INSERT INTO" in call[0])
    assert "'admin'" in insert_call[0]
    assert insert_call[1] == (
        "initial_admin",
        "admin@example.com",
        "argon2id-hash",
    )
    assert PASSWORD not in insert_call[1]
