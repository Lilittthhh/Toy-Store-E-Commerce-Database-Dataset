from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from api.main import app


PRESENTATION_EMAIL = "presentation.customer@example.com"
CATALOG = {
    "The Original Mr. Fuzzy": {
        "description": "A featured toy from the original Toy Store product collection, presented in the RetailMetrics storefront for demonstration.",
        "current_price_usd": "49.99", "current_cogs_usd": "19.49",
    },
    "The Forever Love Bear": {
        "description": "A bear-themed product from the original Toy Store collection, available in the RetailMetrics demonstration storefront.",
        "current_price_usd": "59.99", "current_cogs_usd": "22.49",
    },
    "The Birthday Sugar Panda": {
        "description": "A panda-themed product from the original Toy Store collection, included in the RetailMetrics demonstration storefront.",
        "current_price_usd": "45.99", "current_cogs_usd": "14.49",
    },
    "The Hudson River Mini bear": {
        "description": "A smaller bear product from the original Toy Store collection, configured for the RetailMetrics demonstration storefront.",
        "current_price_usd": "29.99", "current_cogs_usd": "9.49",
    },
}


class SetupError(RuntimeError):
    pass


def _body(response, label: str) -> Any:
    if response.is_success:
        return response.json() if response.content else None
    try:
        detail = response.json().get("detail", "request refused")
    except ValueError:
        detail = "non-JSON API response"
    raise SetupError(f"{label} failed with HTTP {response.status_code}: {detail}")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def configure_catalog(client: TestClient, admin_token: str) -> list[int]:
    headers = _bearer(admin_token)
    rows = _body(client.get("/admin/catalog", headers=headers), "Catalog lookup")
    by_name = {row["product_name"]: row for row in rows}
    if set(by_name) != set(CATALOG):
        raise SetupError("The source catalog does not contain exactly the four approved products.")
    configured: list[int] = []
    for name, approved in CATALOG.items():
        current = by_name[name]
        payload = {**approved, "image_url": None, "is_available": True, "row_version": current["row_version"]}
        updated = _body(
            client.put(f"/admin/catalog/{current['product_id']}", headers=headers, json=payload),
            f"Catalog configuration for {name}",
        )
        if updated["product_name"] != name or updated["image_url"] is not None:
            raise SetupError(f"Catalog response verification failed for {name}.")
        configured.append(updated["product_id"])
    return configured


def ensure_customer(client: TestClient, password: str) -> tuple[int, str]:
    registration = client.post("/customer/auth/register", json={
        "email": PRESENTATION_EMAIL, "password": password,
        "first_name": "Presentation", "last_name": "Customer", "phone": None,
    })
    if registration.status_code not in {201, 409}:
        _body(registration, "Presentation customer registration")
    login = _body(client.post("/customer/auth/login", json={"email": PRESENTATION_EMAIL, "password": password}), "Presentation customer login")
    token = login["access_token"]
    identity = _body(client.get("/customer/auth/me", headers=_bearer(token)), "Presentation customer identity")
    if identity["first_name"] != "Presentation" or identity["last_name"] != "Customer":
        raise SetupError("The configured email belongs to a different customer identity.")
    return identity["customer_account_id"], token


def ensure_resources(client: TestClient, token: str) -> tuple[int, int]:
    headers = _bearer(token)
    addresses = _body(client.get("/customer/addresses", headers=headers), "Address lookup")
    presentation_addresses = [row for row in addresses if row["label"] == "Presentation Address"]
    if len(presentation_addresses) > 1:
        raise SetupError("Multiple presentation addresses exist; resolve them manually before setup.")
    if presentation_addresses:
        address = presentation_addresses[0]
    else:
        address = _body(client.post("/customer/addresses", headers=headers, json={
            "label": "Presentation Address", "recipient_first_name": "Presentation",
            "recipient_last_name": "Customer", "phone": None,
            "address_line_1": "1 Demonstration Lane", "address_line_2": None,
            "city": "Manila", "province_region": "Metro Manila",
            "postal_code": "1000", "country_code": "PH", "is_default": True,
        }), "Presentation address creation")

    methods = _body(client.get("/customer/payment-methods", headers=headers), "Payment-method lookup")
    presentation_methods = [row for row in methods if row["method_type"] == "card" and row.get("card_last_four") == "0000"]
    if len(presentation_methods) > 1:
        raise SetupError("Multiple presentation payment methods exist; resolve them manually before setup.")
    if presentation_methods:
        payment = presentation_methods[0]
    else:
        payment = _body(client.post("/customer/payment-methods", headers=headers, json={
            "method_type": "card", "card_brand": "Demo Card",
            "card_last_four": "0000", "is_default": True,
        }), "Simulated payment-method creation")
    return address["customer_address_id"], payment["payment_method_id"]


def verify_clean_start(client: TestClient, token: str) -> None:
    headers = _bearer(token)
    cart = _body(client.get("/customer/cart", headers=headers), "Cart verification")
    orders = _body(client.get("/customer/orders", headers=headers), "Order verification")
    requests = _body(client.get("/customer/refund-requests", headers=headers), "Refund-request verification")
    if cart["items"] or orders or requests:
        raise SetupError("Presentation customer is not at a clean starting state. Use the targeted reset procedure before presenting.")


def main() -> int:
    print("RetailMetrics presentation setup")
    print("Passwords are collected with hidden input and are never printed or stored by this script.")
    admin_identifier = input("Existing Admin username or email [admin]: ").strip() or "admin"
    admin_password = getpass.getpass("Existing Admin password: ")
    customer_password = getpass.getpass(f"Password for {PRESENTATION_EMAIL}: ")
    customer_confirmation = getpass.getpass("Confirm presentation customer password: ")
    if customer_password != customer_confirmation:
        raise SetupError("Customer password confirmation did not match.")
    with TestClient(app) as client:
        admin_login = _body(client.post("/auth/login", json={"identifier": admin_identifier, "password": admin_password}), "Admin login")
        configured = configure_catalog(client, admin_login["access_token"])
        customer_id, customer_token = ensure_customer(client, customer_password)
        address_id, payment_id = ensure_resources(client, customer_token)
        verify_clean_start(client, customer_token)
    print("Presentation setup completed successfully.")
    print(f"Catalog product IDs configured: {', '.join(map(str, configured))}")
    print(f"Presentation customer ID: {customer_id}")
    print(f"Presentation address ID: {address_id}")
    print(f"Simulated payment method ID: {payment_id}")
    print("Verified: empty cart, no customer orders, and no refund requests.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SetupError, KeyboardInterrupt) as exc:
        print(f"Setup stopped safely: {exc}", file=sys.stderr)
        raise SystemExit(1)
