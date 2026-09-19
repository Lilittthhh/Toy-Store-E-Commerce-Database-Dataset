from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

import psycopg2
from email_validator import EmailNotValidError, validate_email
from pydantic import SecretStr


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.security import hash_password  # noqa: E402
from api.schemas.auth import validate_password_strength  # noqa: E402
from scripts.migration_support import (  # noqa: E402
    connection_settings,
    print_postgresql_error,
    public_connection_summary,
)


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


class BootstrapRefused(RuntimeError):
    """Raised when the database is not eligible for initial Admin creation."""


def validate_credentials(username: str, email: str, password: str) -> tuple[str, str]:
    normalized_username = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise ValueError(
            "Username must be 3-64 characters using letters, numbers, '.', '_', or '-'."
        )
    try:
        normalized_email = validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(f"Invalid email address: {exc}") from exc
    validate_password_strength(SecretStr(password))
    return normalized_username, normalized_email


def create_initial_admin(conn, username: str, email: str, password: str) -> int:
    username, email = validate_credentials(username, email, password)
    password_hash = hash_password(password)

    try:
        with conn:
            with conn.cursor() as cur:
                # Serialize bootstrap eligibility checks with app-user writes so
                # two concurrent bootstrap processes cannot both create Admins.
                cur.execute("LOCK TABLE public.app_users IN SHARE ROW EXCLUSIVE MODE")
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM public.app_users
                        WHERE role = 'admin' AND is_active
                    )
                    """
                )
                if cur.fetchone()[0]:
                    raise BootstrapRefused(
                        "An active Admin already exists; initial bootstrap is disabled."
                    )

                cur.execute(
                    """
                    SELECT username, email
                    FROM public.app_users
                    WHERE LOWER(username) = LOWER(%s)
                       OR LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (username, email),
                )
                duplicate = cur.fetchone()
                if duplicate:
                    raise BootstrapRefused(
                        "The requested username or email is already registered."
                    )

                cur.execute(
                    """
                    INSERT INTO public.app_users
                        (username, email, password_hash, role)
                    VALUES (%s, %s, %s, 'admin')
                    RETURNING app_user_id
                    """,
                    (username, email, password_hash),
                )
                return int(cur.fetchone()[0])
    except psycopg2.errors.UniqueViolation as exc:
        raise BootstrapRefused(
            "The requested username or email was registered concurrently."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the first active RetailMetricsWeb Admin account."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive database-name confirmation.",
    )
    return parser.parse_args()


def read_credentials() -> tuple[str, str, str]:
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")

    if not username:
        username = input("Admin username: ").strip()
    if not email:
        email = input("Admin email: ").strip()
    if not password:
        password = getpass.getpass("Admin password: ")
        confirmation = getpass.getpass("Confirm Admin password: ")
        if password != confirmation:
            raise ValueError("Password confirmation did not match")
    return username, email, password


def main() -> int:
    args = parse_args()
    try:
        settings = connection_settings()
        username, email, password = read_credentials()
        username, email = validate_credentials(username, email, password)
    except (EOFError, KeyboardInterrupt):
        print("\nAdmin bootstrap cancelled before connecting.")
        return 1
    except (TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("RetailMetricsWeb initial Admin bootstrap")
    print(f"Target:   {public_connection_summary(settings)}")
    print(f"Username: {username}")
    print(f"Email:    {email}")
    print("The password and password hash will not be displayed.")

    if not args.yes:
        try:
            confirmation = input(
                f"Type the database name '{settings['dbname']}' to create the Admin: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAdmin bootstrap cancelled before connecting.")
            return 1
        if confirmation != settings["dbname"]:
            print("Admin bootstrap cancelled: database name did not match.")
            return 1

    conn = None
    try:
        conn = psycopg2.connect(**settings)
        app_user_id = create_initial_admin(conn, username, email, password)
        print(f"Initial Admin created successfully with app_user_id={app_user_id}.")
        return 0
    except BootstrapRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except psycopg2.Error as exc:
        print_postgresql_error(exc)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
