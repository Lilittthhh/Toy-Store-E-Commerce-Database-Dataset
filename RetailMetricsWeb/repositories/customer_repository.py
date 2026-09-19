from __future__ import annotations

from typing import Protocol

from psycopg2 import errors
from psycopg2.extensions import connection

from core.models import CustomerAccount, CustomerIdentity, CustomerProfile


ACCOUNT_COLUMNS = """
    customer_account_id, dataset_user_id, email, password_hash, is_active,
    failed_login_attempts, locked_until, last_login_at, password_changed_at,
    password_reset_token_hash, password_reset_expires_at, token_version,
    row_version, created_at, updated_at
"""
ACCOUNT_COLUMNS_FROM_ACCOUNTS = """
    accounts.customer_account_id, accounts.dataset_user_id, accounts.email,
    accounts.password_hash, accounts.is_active, accounts.failed_login_attempts,
    accounts.locked_until, accounts.last_login_at, accounts.password_changed_at,
    accounts.password_reset_token_hash, accounts.password_reset_expires_at,
    accounts.token_version, accounts.row_version, accounts.created_at,
    accounts.updated_at
"""
PROFILE_COLUMNS = """
    customer_account_id, first_name, last_name, phone, row_version,
    created_at, updated_at
"""


class DuplicateCustomerEmail(ValueError):
    pass


class CustomerRepository(Protocol):
    def create_with_profile(self, email: str, password_hash: str, first_name: str, last_name: str, phone: str | None) -> CustomerIdentity: ...
    def get_by_id(self, customer_account_id: int) -> CustomerAccount | None: ...
    def get_by_email(self, email: str) -> CustomerAccount | None: ...
    def get_profile(self, customer_account_id: int) -> CustomerProfile | None: ...
    def get_identity(self, customer_account_id: int) -> CustomerIdentity | None: ...
    def record_failed_login(self, customer_account_id: int, limit: int, lock_seconds: int) -> CustomerAccount: ...
    def record_successful_login(self, customer_account_id: int, replacement_hash: str | None) -> CustomerAccount: ...
    def increment_token_version(self, customer_account_id: int) -> CustomerAccount: ...
    def change_password(self, customer_account_id: int, password_hash: str) -> CustomerAccount: ...
    def store_reset_token(self, customer_account_id: int, token_hash: str, lifetime_seconds: int) -> None: ...
    def reset_password(self, token_hash: str, password_hash: str) -> CustomerAccount | None: ...
    def update_profile(self, customer_account_id: int, first_name: str, last_name: str, phone: str | None, row_version: int) -> CustomerProfile | None: ...
    def list_identities(self, search: str | None, is_active: bool | None, limit: int, offset: int) -> tuple[list[CustomerIdentity], int]: ...
    def update_active(self, customer_account_id: int, is_active: bool, row_version: int) -> CustomerAccount | None: ...
    def unlock(self, customer_account_id: int, row_version: int) -> CustomerAccount | None: ...


def _account_from_row(row) -> CustomerAccount:
    return CustomerAccount(
        customer_account_id=int(row[0]), dataset_user_id=int(row[1]) if row[1] is not None else None,
        email=row[2], password_hash=row[3], is_active=bool(row[4]),
        failed_login_attempts=int(row[5]), locked_until=row[6], last_login_at=row[7],
        password_changed_at=row[8], password_reset_token_hash=row[9],
        password_reset_expires_at=row[10], token_version=int(row[11]),
        row_version=int(row[12]), created_at=row[13], updated_at=row[14],
    )


def _profile_from_row(row) -> CustomerProfile:
    return CustomerProfile(
        customer_account_id=int(row[0]), first_name=row[1], last_name=row[2],
        phone=row[3], row_version=int(row[4]), created_at=row[5], updated_at=row[6],
    )


class PostgresCustomerRepository:
    def __init__(self, conn: connection):
        self.conn = conn

    def _fetch_account(self, query: str, parameters: tuple) -> CustomerAccount | None:
        with self.conn.cursor() as cur:
            cur.execute(query, parameters)
            row = cur.fetchone()
        return _account_from_row(row) if row else None

    def _fetch_profile(self, query: str, parameters: tuple) -> CustomerProfile | None:
        with self.conn.cursor() as cur:
            cur.execute(query, parameters)
            row = cur.fetchone()
        return _profile_from_row(row) if row else None

    def create_with_profile(self, email: str, password_hash: str, first_name: str, last_name: str, phone: str | None) -> CustomerIdentity:
        try:
            account = self._fetch_account(
                f"""INSERT INTO public.customer_accounts (email, password_hash)
                    VALUES (%s, %s) RETURNING {ACCOUNT_COLUMNS}""",
                (email, password_hash),
            )
            assert account is not None
            profile = self._fetch_profile(
                f"""INSERT INTO public.customer_profiles
                    (customer_account_id, first_name, last_name, phone)
                    VALUES (%s, %s, %s, %s) RETURNING {PROFILE_COLUMNS}""",
                (account.customer_account_id, first_name, last_name, phone),
            )
        except errors.UniqueViolation as exc:
            raise DuplicateCustomerEmail("A customer account already uses that email.") from exc
        assert profile is not None
        return CustomerIdentity(account, profile)

    def get_by_id(self, customer_account_id: int) -> CustomerAccount | None:
        return self._fetch_account(
            f"SELECT {ACCOUNT_COLUMNS} FROM public.customer_accounts WHERE customer_account_id=%s",
            (customer_account_id,),
        )

    def get_by_email(self, email: str) -> CustomerAccount | None:
        return self._fetch_account(
            f"SELECT {ACCOUNT_COLUMNS} FROM public.customer_accounts WHERE LOWER(email)=LOWER(%s)",
            (email,),
        )

    def get_profile(self, customer_account_id: int) -> CustomerProfile | None:
        return self._fetch_profile(
            f"SELECT {PROFILE_COLUMNS} FROM public.customer_profiles WHERE customer_account_id=%s",
            (customer_account_id,),
        )

    def get_identity(self, customer_account_id: int) -> CustomerIdentity | None:
        account = self.get_by_id(customer_account_id)
        profile = self.get_profile(customer_account_id) if account else None
        return CustomerIdentity(account, profile) if account and profile else None

    def record_failed_login(self, customer_account_id: int, limit: int, lock_seconds: int) -> CustomerAccount:
        account = self._fetch_account(
            f"""WITH current_state AS (
                    SELECT customer_account_id,
                           CASE WHEN locked_until IS NOT NULL AND locked_until <= NOW()
                                THEN 0 ELSE failed_login_attempts END AS previous_attempts
                    FROM public.customer_accounts WHERE customer_account_id=%s FOR UPDATE
                )
                UPDATE public.customer_accounts AS accounts
                SET failed_login_attempts=current_state.previous_attempts + 1,
                    locked_until=CASE WHEN current_state.previous_attempts + 1 >= %s
                        THEN NOW() + (%s * INTERVAL '1 second') ELSE NULL END,
                    row_version=accounts.row_version + 1, updated_at=NOW()
                FROM current_state
                WHERE accounts.customer_account_id=current_state.customer_account_id
                RETURNING {ACCOUNT_COLUMNS_FROM_ACCOUNTS}""",
            (customer_account_id, limit, lock_seconds),
        )
        assert account is not None
        self.conn.commit()
        return account

    def record_successful_login(self, customer_account_id: int, replacement_hash: str | None) -> CustomerAccount:
        account = self._fetch_account(
            f"""UPDATE public.customer_accounts
                SET failed_login_attempts=0, locked_until=NULL, last_login_at=NOW(),
                    password_hash=COALESCE(%s, password_hash), row_version=row_version + 1,
                    updated_at=NOW() WHERE customer_account_id=%s RETURNING {ACCOUNT_COLUMNS}""",
            (replacement_hash, customer_account_id),
        )
        assert account is not None
        return account

    def increment_token_version(self, customer_account_id: int) -> CustomerAccount:
        account = self._fetch_account(
            f"""UPDATE public.customer_accounts SET token_version=token_version + 1,
                    row_version=row_version + 1, updated_at=NOW()
                WHERE customer_account_id=%s RETURNING {ACCOUNT_COLUMNS}""",
            (customer_account_id,),
        )
        assert account is not None
        return account

    def change_password(self, customer_account_id: int, password_hash: str) -> CustomerAccount:
        account = self._fetch_account(
            f"""UPDATE public.customer_accounts SET password_hash=%s,
                    password_changed_at=NOW(), password_reset_token_hash=NULL,
                    password_reset_expires_at=NULL, failed_login_attempts=0,
                    locked_until=NULL, token_version=token_version + 1,
                    row_version=row_version + 1, updated_at=NOW()
                WHERE customer_account_id=%s RETURNING {ACCOUNT_COLUMNS}""",
            (password_hash, customer_account_id),
        )
        assert account is not None
        return account

    def store_reset_token(self, customer_account_id: int, token_hash: str, lifetime_seconds: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE public.customer_accounts SET password_reset_token_hash=%s,
                       password_reset_expires_at=NOW() + (%s * INTERVAL '1 second'),
                       row_version=row_version + 1, updated_at=NOW()
                   WHERE customer_account_id=%s AND is_active""",
                (token_hash, lifetime_seconds, customer_account_id),
            )

    def reset_password(self, token_hash: str, password_hash: str) -> CustomerAccount | None:
        return self._fetch_account(
            f"""UPDATE public.customer_accounts SET password_hash=%s,
                    password_changed_at=NOW(), password_reset_token_hash=NULL,
                    password_reset_expires_at=NULL, failed_login_attempts=0,
                    locked_until=NULL, token_version=token_version + 1,
                    row_version=row_version + 1, updated_at=NOW()
                WHERE password_reset_token_hash=%s AND password_reset_expires_at > NOW()
                  AND is_active RETURNING {ACCOUNT_COLUMNS}""",
            (password_hash, token_hash),
        )

    def update_profile(self, customer_account_id: int, first_name: str, last_name: str, phone: str | None, row_version: int) -> CustomerProfile | None:
        return self._fetch_profile(
            f"""UPDATE public.customer_profiles SET first_name=%s, last_name=%s,
                    phone=%s, row_version=row_version + 1, updated_at=NOW()
                WHERE customer_account_id=%s AND row_version=%s RETURNING {PROFILE_COLUMNS}""",
            (first_name, last_name, phone, customer_account_id, row_version),
        )

    def list_identities(self, search: str | None, is_active: bool | None, limit: int, offset: int) -> tuple[list[CustomerIdentity], int]:
        clauses: list[str] = []
        params: list = []
        if search:
            clauses.append("(a.email ILIKE %s OR p.first_name ILIKE %s OR p.last_name ILIKE %s)")
            pattern = f"%{search.strip()}%"
            params.extend((pattern, pattern, pattern))
        if is_active is not None:
            clauses.append("a.is_active=%s")
            params.append(is_active)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.customer_accounts a JOIN public.customer_profiles p USING (customer_account_id)" + where, params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"""SELECT {ACCOUNT_COLUMNS_FROM_ACCOUNTS},
                           p.customer_account_id, p.first_name, p.last_name, p.phone,
                           p.row_version, p.created_at, p.updated_at
                    FROM public.customer_accounts accounts
                    JOIN public.customer_profiles p USING (customer_account_id)
                    {where.replace('a.', 'accounts.')}
                    ORDER BY accounts.customer_account_id DESC LIMIT %s OFFSET %s""",
                [*params, limit, offset],
            )
            rows = cur.fetchall()
        return [CustomerIdentity(_account_from_row(row[:15]), _profile_from_row(row[15:])) for row in rows], total

    def update_active(self, customer_account_id: int, is_active: bool, row_version: int) -> CustomerAccount | None:
        return self._fetch_account(
            f"""UPDATE public.customer_accounts SET is_active=%s,
                    token_version=token_version + 1, row_version=row_version + 1,
                    updated_at=NOW() WHERE customer_account_id=%s AND row_version=%s
                RETURNING {ACCOUNT_COLUMNS}""",
            (is_active, customer_account_id, row_version),
        )

    def unlock(self, customer_account_id: int, row_version: int) -> CustomerAccount | None:
        return self._fetch_account(
            f"""UPDATE public.customer_accounts SET failed_login_attempts=0,
                    locked_until=NULL, row_version=row_version + 1, updated_at=NOW()
                WHERE customer_account_id=%s AND row_version=%s RETURNING {ACCOUNT_COLUMNS}""",
            (customer_account_id, row_version),
        )
