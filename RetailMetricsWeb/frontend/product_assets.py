from __future__ import annotations

from pathlib import Path


PRODUCT_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "products"

PRODUCT_IMAGE_FILES = {
    "The Original Mr. Fuzzy": "original-mr-fuzzy.webp",
    "The Forever Love Bear": "forever-love-bear.webp",
    "The Birthday Sugar Panda": "birthday-sugar-panda.webp",
    "The Hudson River Mini bear": "hudson-river-mini-bear.webp",
}


def product_image_path(product_name: str) -> Path | None:
    """Return the bundled storefront image for a known catalog product."""
    filename = PRODUCT_IMAGE_FILES.get(product_name)
    if not filename:
        return None
    path = PRODUCT_ASSET_DIR / filename
    return path if path.is_file() else None
