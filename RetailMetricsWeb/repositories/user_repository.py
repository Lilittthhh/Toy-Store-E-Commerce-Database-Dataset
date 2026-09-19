from __future__ import annotations

from typing import Protocol

from psycopg2 import errors
from psycopg2.extensions import connection

from core.models import AppUser, Role


USER_COLUMNS = """
    app_user_id, username, email, password_hash, role, is_active,
    failed_login_attempts, locked_until, last_login_at, password_changed_at,
    token_version, row_version, created_at, updated_at
"""
USER_COLUMNS_FROM_USERS = """
    users.app_user_id, users.username, users.email, users.password_hash,
    users.role, users.is_active, users.failed_login_attempts,
    users.locked_until, users.last_login_at, users.password_changed_at,
    users.token_version, users.row_version, users.created_at, users.updated_at
"""


class DuplicateUserIdentity(ValueError):
    pass


class UserRepository(Protocol):
    def create_analyst(self, username: str, email: str, password_hash: str) -> AppUser: ...
    def get_by_id(self, app_user_id: int) -> AppUser | None: ...
    def get_by_login(self, identifier: str) -> AppUser | None: ...
    def get_by_email(self, email: str) -> AppUser | None: ...
    def record_failed_login(self, app_user_id: int, limit: int, lock_seconds: int) -> AppUser: ...
    def record_successful_login(self, app_user_id: int, replacement_hash: str | None) -> AppUser: ...
    def increment_token_version(self, app_user_id: int) -> AppUser: ...
    def change_password(self, app_user_id: int, password_hash: str) -> AppUser: ...
    def store_reset_token(self, app_user_id: int, token_hash: str, lifetime_seconds: int) -> None: ...
    def reset_password(self, token_hash: str, password_hash: str) -> AppUser | None: ...
    def list_users(self, search: str | None, role: Role | None, is_active: bool | None, limit: int, offset: int) -> tuple[list[AppUser], int]: ...
    def create_user(self, username: str, email: str, password_hash: str, role: Role) -> AppUser: ...
    def update_role(self, app_user_id: int, role: Role, row_version: int) -> AppUser | None: ...
    def update_active(self, app_user_id: int, is_active: bool, row_version: int) -> AppUser | None: ...
    def unlock(self, app_user_id: int, row_version: int) -> AppUser | None: ...
    def count_active_admins_locked(self) -> int: ...


def _user_from_row(row) -> AppUser:
    return AppUser(
        app_user_id=int(row[0]),
        username=row[1],
        email=row[2],
        password_hash=row[3],
        role=Role(row[4]),
        is_active=bool(row[5]),
        failed_login_attempts=int(row[6]),
        locked_until=row[7],
        last_login_at=row[8],
        password_changed_at=row[9],
        token_version=int(row[10]),
        row_version=int(row[11]),
        created_at=row[12],
        updated_at=row[13],
    )


class PostgresUserRepository:
    def __init__(self, conn: connection):
        self.conn = conn

    def _fetch_user(self, query: str, parameters: tuple) -> AppUser | None:
        with self.conn.cursor() as cur:
            cur.execute(query, parameters)
            row = cur.fetchone()
        return _user_from_row(row) if row else None

    def create_analyst(self, username: str, email: str, password_hash: str) -> AppUser:
        try:
            user = self._fetch_user(
                f"""
                INSERT INTO public.app_users (username, email, password_hash, role)
                VALUES (%s, %s, %s, 'analyst')
                RETURNING {USER_COLUMNS}
                """,
                (username, email, password_hash),
            )
        except errors.UniqueViolation as exc:
            raise DuplicateUserIdentity("Username or email is already registered") from exc
        assert user is not None
        return user

    def list_users(
        self,
        search: str | None,
        role: Role | None,
        is_active: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AppUser], int]:
        clauses: list[str] = []
        params: list = []
        if search:
            clauses.append("(username ILIKE %s OR email ILIKE %s)")
            pattern = f"%{search.strip()}%"
            params.extend((pattern, pattern))
        if role is not None:
            clauses.append("role = %s")
            params.append(role.value)
        if is_active is not None:
            clauses.append("is_active = %s")
            params.append(is_active)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.app_users" + where, params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"SELECT {USER_COLUMNS} FROM public.app_users"
                + where
                + " ORDER BY app_user_id DESC LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            users = [_user_from_row(row) for row in cur.fetchall()]
        return users, total

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: Role,
    ) -> AppUser:
        try:
            user = self._fetch_user(
                f"""
                INSERT INTO public.app_users (username, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                RETURNING {USER_COLUMNS}
                """,
                (username, email, password_hash, role.value),
            )
        except errors.UniqueViolation as exc:
            raise DuplicateUserIdentity("Username or email is already registered") from exc
        assert user is not None
        return user

    def update_role(
        self,
        app_user_id: int,
        role: Role,
        row_version: int,
    ) -> AppUser | None:
        return self._fetch_user(
            f"""
            UPDATE public.app_users
            SET role = %s,
                token_version = token_version + 1,
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE app_user_id = %s AND row_version = %s
            RETURNING {USER_COLUMNS}
            """,
            (role.value, app_user_id, row_version),
        )

    def update_active(
        self,
        app_user_id: int,
        is_active: bool,
        row_version: int,
    ) -> AppUser | None:
        return self._fetch_user(
            f"""
            UPDATE public.app_users
            SET is_active = %s,
                token_version = token_version + 1,
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE app_user_id = %s AND row_version = %s
            RETURNING {USER_COLUMNS}
            """,
            (is_active, app_user_id, row_version),
        )

    def unlock(self, app_user_id: int, row_version: int) -> AppUser | None:
        return self._fetch_user(
            f"""
            UPDATE public.app_users
            SET failed_login_attempts = 0,
                locked_until = NULL,
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE app_user_id = %s AND row_version = %s
            RETURNING {USER_COLUMNS}
            """,
            (app_user_id, row_version),
        )

    def count_active_admins_locked(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_user_id
                FROM public.app_users
                WHERE role = 'admin' AND is_active
                FOR UPDATE
                """
            )
            return len(cur.fetchall())

    def get_by_id(self, app_user_id: int) -> AppUser | None:
        return self._fetch_user(
            f"SELECT {USER_COLUMNS} FROM public.app_users WHERE app_user_id = %s",
            (app_user_id,),
        )

    def get_by_login(self, identifier: str) -> AppUser | None:
        return self._fetch_user(
            f"""
            SELECT {USER_COLUMNS}
            FROM public.app_users
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
            """,
            (identifier, identifier),
        )

    def get_by_email(self, email: str) -> AppUser | None:
        return self._fetch_user(
            f"""
            SELECT {USER_COLUMNS}
            FROM public.app_users
            WHERE LOWER(email) = LOWER(%s)
            """,
            (email,),
        )

    def record_failed_login(
        self,
        app_user_id: int,
        limit: int,
        lock_seconds: int,
    ) -> AppUser:
        user = self._fetch_user(
            f"""
            WITH current_state AS (
                SELECT
                    app_user_id,
                    CASE
                        WHEN locked_until IS NOT NULL AND locked_until <= NOW() THEN 0
                        ELSE failed_login_attempts
                    END AS previous_attempts
                FROM public.app_users
                WHERE app_user_id = %s
                FOR UPDATE
            )
            UPDATE public.app_users AS users
            SET failed_login_attempts = current_state.previous_attempts + 1,
                locked_until = CASE
                    WHEN current_state.previous_attempts + 1 >= %s
                    THEN NOW() + (%s * INTERVAL '1 second')
                    ELSE NULL
                END,
                row_version = users.row_version + 1,
                updated_at = NOW()
            FROM current_state
            WHERE users.app_user_id = current_state.app_user_id
            RETURNING {USER_COLUMNS_FROM_USERS}
            """,
            (app_user_id, limit, lock_seconds),
        )
        assert user is not None
        # The service deliberately raises 401/423 after this update. Commit the
        # security event here so the request dependency's exception rollback
        # cannot discard the failed-attempt counter or temporary lock.
        self.conn.commit()
        return user

    def record_successful_login(
        self,
        app_user_id: int,
        replacement_hash: str | None,
    ) -> AppUser:
        user = self._fetch_user(
            f"""
            UPDATE public.app_users
            SET failed_login_attempts = 0,
                locked_until = NULL,
                last_login_at = NOW(),
                password_hash = COALESCE(%s, password_hash),
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE app_user_id = %s
            RETURNING {USER_COLUMNS}
            """,
            (replacement_hash, app_user_id),
        )
        assert user is not None
        return user

    def increment_token_version(self, app_user_id: int) -> AppUser:
        user = self._fetch_user(
            f"""
            UPDATE public.app_users
            SET token_version = token_version + 1,
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE app_user_id = %s
            RETURNING {USER_COLUMNS}
            """,
            (app_user_id,),
        )
        assert user is not None
        return user

    def change_password(self, app_user_id: int, password_hash: str) -> AppUser:
        user = self._fetch_user(
            f"""
            UPDATE public.app_users
            SET password_hash = %s,
                password_changed_at = NOW(),
                password_reset_token_hash = NULL,
                password_reset_expires_at = NULL,
                failed_login_attempts = 0,
                locked_until = NULL,
                token_version = token_version + 1,
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE app_user_id = %s
            RETURNING {USER_COLUMNS}
            """,
            (password_hash, app_user_id),
        )
        assert user is not None
        return user

    def store_reset_token(
        self,
        app_user_id: int,
        token_hash: str,
        lifetime_seconds: int,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.app_users
                SET password_reset_token_hash = %s,
                    password_reset_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    row_version = row_version + 1,
                    updated_at = NOW()
                WHERE app_user_id = %s AND is_active
                """,
                (token_hash, lifetime_seconds, app_user_id),
            )

    def reset_password(self, token_hash: str, password_hash: str) -> AppUser | None:
        return self._fetch_user(
            f"""
            UPDATE public.app_users
            SET password_hash = %s,
                password_changed_at = NOW(),
                password_reset_token_hash = NULL,
                password_reset_expires_at = NULL,
                failed_login_attempts = 0,
                locked_until = NULL,
                token_version = token_version + 1,
                row_version = row_version + 1,
                updated_at = NOW()
            WHERE password_reset_token_hash = %s
              AND password_reset_expires_at > NOW()
              AND is_active
            RETURNING {USER_COLUMNS}
            """,
            (password_hash, token_hash),
        )
