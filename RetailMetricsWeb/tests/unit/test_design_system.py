from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
CSS = (APP_ROOT / "frontend" / "assets" / "retailmetrics.css").read_text(encoding="utf-8")
UI = (APP_ROOT / "frontend" / "ui.py").read_text(encoding="utf-8")
NAVIGATION = (APP_ROOT / "frontend" / "navigation.py").read_text(encoding="utf-8")


def test_design_system_is_centralized_and_tokenized():
    for token in (
        "--rm-ink", "--rm-accent", "--rm-canvas", "--rm-surface",
        "--rm-line", "--rm-success", "--rm-warning", "--rm-danger",
    ):
        assert token in CSS
    assert "DESIGN_SYSTEM_PATH" in UI
    assert "summary_strip" in UI


def test_design_system_has_required_responsive_breakpoints_and_safe_overflow():
    assert "@media (max-width: 1100px)" in CSS
    assert "@media (max-width: 768px)" in CSS
    assert "@media (max-width: 430px)" in CSS
    assert "overflow-x:auto" in CSS.replace(" ", "")
    assert "flex-wrap:wrap" in CSS.replace(" ", "")


def test_shell_hides_only_nonessential_streamlit_chrome_and_keeps_sidebar():
    assert '[data-testid="stToolbar"]' in CSS
    assert '[data-testid="stSidebar"]' in CSS
    assert "min-width: 216px" in CSS
    assert "display: none" not in CSS.split('[data-testid="stSidebar"]', 1)[1].split("}", 1)[0]


def test_authenticated_shell_keeps_native_sidebar_reopen_control_available():
    control_rule = CSS.split('[data-testid="stSidebarCollapsedControl"]', 1)[1].split("}", 1)[0]
    assert "display:flex !important" in control_rule
    assert "position:fixed" in control_rule
    assert '[data-testid="stSidebarCollapseButton"]' in CSS
    assert ".rm-mobile-topbar" in CSS


def test_notification_readiness_is_a_checklist_not_a_table():
    source = (APP_ROOT / "frontend" / "views" / "notification_test.py").read_text(encoding="utf-8")
    assert "readiness_checklist" in source
    assert "st.table(" not in source


def test_customer_uses_a_distinct_website_shell_without_sidebar_navigation():
    customer_navigation = NAVIGATION.split("def render_customer_navigation", 1)[1].split(
        "def render_staff_navigation", 1
    )[0]
    assert "st.sidebar" not in customer_navigation
    assert "customer_site_header" in customer_navigation
    assert "customer_mobile_header" in customer_navigation
    assert ".stApp:has(.rm-customer-shell-marker) [data-testid=\"stSidebar\"]" in CSS


def test_customer_shell_has_desktop_and_mobile_navigation_presentations():
    assert '[class*="st-key-customer_site_header"]' in CSS
    assert '[class*="st-key-customer_mobile_header"]' in CSS
    mobile = CSS.split("@media (max-width:768px)", 1)[1]
    assert '[class*="st-key-customer_site_header"]{display:none}' in mobile
    assert '[class*="st-key-customer_mobile_header"]' in mobile


def test_public_storefront_has_rich_landing_sections_and_responsive_layout():
    source = (APP_ROOT / "frontend" / "views" / "public_storefront.py").read_text(encoding="utf-8")
    for section in ("rm-public-hero", "rm-public-benefits", "rm-public-product-marker",
                    "rm-public-review-section", "rm-public-cta"):
        assert section in source
        assert section in CSS
    assert "Browse before joining" in source
    assert "Sign in to checkout" in source
    assert "@media (max-width: 900px)" in CSS


def test_generated_product_images_are_bundled_and_mapped():
    assets = APP_ROOT / "frontend" / "assets" / "products"
    mapping = (APP_ROOT / "frontend" / "product_assets.py").read_text(encoding="utf-8")
    expected = {
        "original-mr-fuzzy.webp", "forever-love-bear.webp",
        "birthday-sugar-panda.webp", "hudson-river-mini-bear.webp",
    }
    assert {path.name for path in assets.glob("*.webp")} == expected
    assert all(name in mapping for name in expected)


def test_visual_language_avoids_decorative_dashboard_patterns():
    lowered = CSS.lower()
    assert "glassmorphism" not in lowered
    assert "backdrop-filter" not in lowered
    assert "linear-gradient" not in lowered
    assert "border-radius:999px" not in lowered.replace(" ", "")


def test_toy_store_palette_and_role_shells_are_present():
    for token in ("--rm-play", "--rm-sun", "--rm-sky", "--rm-staff-sidebar"):
        assert token in CSS
    assert ".rm-staff-role-admin" in CSS
    assert ".rm-staff-role-operations_staff" in CSS
    assert ".rm-staff-role-analyst" in CSS
    assert ".rm-customer-ribbon" in CSS
    assert "render_staff_workspace_banner" in UI
