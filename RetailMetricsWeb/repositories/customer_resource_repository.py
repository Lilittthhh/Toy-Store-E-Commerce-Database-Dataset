from __future__ import annotations

from typing import Any, Protocol

from psycopg2.extensions import connection

from core.models import CustomerAddress, PaymentMethod


ADDRESS_COLUMNS = """customer_address_id, customer_account_id, label, recipient_first_name,
recipient_last_name, phone, address_line_1, address_line_2, city, province_region,
postal_code, country_code, is_default, is_active, row_version, created_at, updated_at"""
PAYMENT_COLUMNS = """payment_method_id, customer_account_id, method_type, display_label,
card_brand, card_last_four, is_default, is_active, row_version, created_at, updated_at"""


def _address(row: tuple[Any, ...]) -> CustomerAddress:
    return CustomerAddress(*row)


def _payment(row: tuple[Any, ...]) -> PaymentMethod:
    values = list(row)
    if values[5] is not None:
        values[5] = values[5].strip()
    return PaymentMethod(*values)


class CustomerResourceRepository(Protocol):
    def list_addresses(self, account_id: int) -> list[CustomerAddress]: ...
    def get_address(self, account_id: int, resource_id: int) -> CustomerAddress | None: ...
    def create_address(self, account_id: int, values: dict[str, Any], make_default: bool) -> CustomerAddress: ...
    def update_address(self, account_id: int, resource_id: int, values: dict[str, Any], version: int) -> CustomerAddress | None: ...
    def set_default_address(self, account_id: int, resource_id: int, version: int) -> CustomerAddress | None: ...
    def deactivate_address(self, account_id: int, resource_id: int, version: int) -> CustomerAddress | None: ...
    def list_payment_methods(self, account_id: int) -> list[PaymentMethod]: ...
    def get_payment_method(self, account_id: int, resource_id: int) -> PaymentMethod | None: ...
    def create_payment_method(self, account_id: int, values: dict[str, Any], make_default: bool) -> PaymentMethod: ...
    def update_payment_method(self, account_id: int, resource_id: int, values: dict[str, Any], version: int) -> PaymentMethod | None: ...
    def set_default_payment_method(self, account_id: int, resource_id: int, version: int) -> PaymentMethod | None: ...
    def deactivate_payment_method(self, account_id: int, resource_id: int, version: int) -> PaymentMethod | None: ...


class PostgresCustomerResourceRepository:
    def __init__(self, conn: connection):
        self.conn = conn

    def _lock_account(self, cur, account_id: int) -> None:
        cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE customer_account_id=%s FOR UPDATE", (account_id,))
        if cur.fetchone() is None:
            raise LookupError("Customer account not found.")

    def list_addresses(self, account_id: int) -> list[CustomerAddress]:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {ADDRESS_COLUMNS} FROM public.customer_addresses WHERE customer_account_id=%s ORDER BY is_active DESC, is_default DESC, customer_address_id", (account_id,))
            return [_address(row) for row in cur.fetchall()]

    def get_address(self, account_id: int, resource_id: int) -> CustomerAddress | None:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {ADDRESS_COLUMNS} FROM public.customer_addresses WHERE customer_account_id=%s AND customer_address_id=%s", (account_id, resource_id))
            row = cur.fetchone()
            return _address(row) if row else None

    def create_address(self, account_id: int, values: dict[str, Any], make_default: bool) -> CustomerAddress:
        columns = tuple(values)
        with self.conn.cursor() as cur:
            self._lock_account(cur, account_id)
            cur.execute("SELECT EXISTS (SELECT 1 FROM public.customer_addresses WHERE customer_account_id=%s AND is_active AND is_default)", (account_id,))
            use_default = make_default or not bool(cur.fetchone()[0])
            if use_default:
                cur.execute("UPDATE public.customer_addresses SET is_default=FALSE, row_version=row_version+1, updated_at=NOW() WHERE customer_account_id=%s AND is_active AND is_default", (account_id,))
            placeholders = ",".join(["%s"] * len(columns))
            cur.execute(f"INSERT INTO public.customer_addresses (customer_account_id,{','.join(columns)},is_default) VALUES (%s,{placeholders},%s) RETURNING {ADDRESS_COLUMNS}", (account_id, *(values[key] for key in columns), use_default))
            return _address(cur.fetchone())

    def update_address(self, account_id: int, resource_id: int, values: dict[str, Any], version: int) -> CustomerAddress | None:
        assignments = ",".join(f"{key}=%s" for key in values)
        with self.conn.cursor() as cur:
            cur.execute(f"UPDATE public.customer_addresses SET {assignments},row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND customer_address_id=%s AND row_version=%s RETURNING {ADDRESS_COLUMNS}", (*(values[key] for key in values), account_id, resource_id, version))
            row = cur.fetchone()
            return _address(row) if row else None

    def set_default_address(self, account_id: int, resource_id: int, version: int) -> CustomerAddress | None:
        with self.conn.cursor() as cur:
            self._lock_account(cur, account_id)
            cur.execute("SELECT row_version,is_active FROM public.customer_addresses WHERE customer_account_id=%s AND customer_address_id=%s FOR UPDATE", (account_id, resource_id))
            row = cur.fetchone()
            if not row or int(row[0]) != version or not row[1]:
                return None
            cur.execute("UPDATE public.customer_addresses SET is_default=FALSE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND is_active AND is_default AND customer_address_id<>%s", (account_id, resource_id))
            cur.execute(f"UPDATE public.customer_addresses SET is_default=TRUE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND customer_address_id=%s AND row_version=%s RETURNING {ADDRESS_COLUMNS}", (account_id, resource_id, version))
            changed = cur.fetchone()
            return _address(changed) if changed else None

    def deactivate_address(self, account_id: int, resource_id: int, version: int) -> CustomerAddress | None:
        with self.conn.cursor() as cur:
            self._lock_account(cur, account_id)
            cur.execute("SELECT row_version,is_default FROM public.customer_addresses WHERE customer_account_id=%s AND customer_address_id=%s FOR UPDATE", (account_id, resource_id))
            state = cur.fetchone()
            if not state or int(state[0]) != version:
                return None
            cur.execute(f"UPDATE public.customer_addresses SET is_active=FALSE,is_default=FALSE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND customer_address_id=%s AND row_version=%s RETURNING {ADDRESS_COLUMNS}", (account_id, resource_id, version))
            changed = cur.fetchone()
            if changed and state[1]:
                cur.execute("UPDATE public.customer_addresses SET is_default=TRUE,row_version=row_version+1,updated_at=NOW() WHERE customer_address_id=(SELECT customer_address_id FROM public.customer_addresses WHERE customer_account_id=%s AND is_active ORDER BY customer_address_id LIMIT 1)", (account_id,))
            return _address(changed) if changed else None

    def list_payment_methods(self, account_id: int) -> list[PaymentMethod]:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {PAYMENT_COLUMNS} FROM public.payment_methods WHERE customer_account_id=%s ORDER BY is_active DESC, is_default DESC, payment_method_id", (account_id,))
            return [_payment(row) for row in cur.fetchall()]

    def get_payment_method(self, account_id: int, resource_id: int) -> PaymentMethod | None:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT {PAYMENT_COLUMNS} FROM public.payment_methods WHERE customer_account_id=%s AND payment_method_id=%s", (account_id, resource_id))
            row = cur.fetchone()
            return _payment(row) if row else None

    def create_payment_method(self, account_id: int, values: dict[str, Any], make_default: bool) -> PaymentMethod:
        columns = tuple(values)
        with self.conn.cursor() as cur:
            self._lock_account(cur, account_id)
            cur.execute("SELECT EXISTS (SELECT 1 FROM public.payment_methods WHERE customer_account_id=%s AND is_active AND is_default)", (account_id,))
            use_default = make_default or not bool(cur.fetchone()[0])
            if use_default:
                cur.execute("UPDATE public.payment_methods SET is_default=FALSE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND is_active AND is_default", (account_id,))
            placeholders = ",".join(["%s"] * len(columns))
            cur.execute(f"INSERT INTO public.payment_methods (customer_account_id,{','.join(columns)},is_default) VALUES (%s,{placeholders},%s) RETURNING {PAYMENT_COLUMNS}", (account_id, *(values[key] for key in columns), use_default))
            return _payment(cur.fetchone())

    def update_payment_method(self, account_id: int, resource_id: int, values: dict[str, Any], version: int) -> PaymentMethod | None:
        assignments = ",".join(f"{key}=%s" for key in values)
        with self.conn.cursor() as cur:
            cur.execute(f"UPDATE public.payment_methods SET {assignments},row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND payment_method_id=%s AND row_version=%s RETURNING {PAYMENT_COLUMNS}", (*(values[key] for key in values), account_id, resource_id, version))
            row = cur.fetchone()
            return _payment(row) if row else None

    def set_default_payment_method(self, account_id: int, resource_id: int, version: int) -> PaymentMethod | None:
        with self.conn.cursor() as cur:
            self._lock_account(cur, account_id)
            cur.execute("SELECT row_version,is_active FROM public.payment_methods WHERE customer_account_id=%s AND payment_method_id=%s FOR UPDATE", (account_id, resource_id))
            row = cur.fetchone()
            if not row or int(row[0]) != version or not row[1]:
                return None
            cur.execute("UPDATE public.payment_methods SET is_default=FALSE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND is_active AND is_default AND payment_method_id<>%s", (account_id, resource_id))
            cur.execute(f"UPDATE public.payment_methods SET is_default=TRUE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND payment_method_id=%s AND row_version=%s RETURNING {PAYMENT_COLUMNS}", (account_id, resource_id, version))
            changed = cur.fetchone()
            return _payment(changed) if changed else None

    def deactivate_payment_method(self, account_id: int, resource_id: int, version: int) -> PaymentMethod | None:
        with self.conn.cursor() as cur:
            self._lock_account(cur, account_id)
            cur.execute("SELECT row_version,is_default FROM public.payment_methods WHERE customer_account_id=%s AND payment_method_id=%s FOR UPDATE", (account_id, resource_id))
            state = cur.fetchone()
            if not state or int(state[0]) != version:
                return None
            cur.execute(f"UPDATE public.payment_methods SET is_active=FALSE,is_default=FALSE,row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND payment_method_id=%s AND row_version=%s RETURNING {PAYMENT_COLUMNS}", (account_id, resource_id, version))
            changed = cur.fetchone()
            if changed and state[1]:
                cur.execute("UPDATE public.payment_methods SET is_default=TRUE,row_version=row_version+1,updated_at=NOW() WHERE payment_method_id=(SELECT payment_method_id FROM public.payment_methods WHERE customer_account_id=%s AND is_active ORDER BY payment_method_id LIMIT 1)", (account_id,))
            return _payment(changed) if changed else None
