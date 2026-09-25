# RetailMetrics web UI

The web frontend serves four audiences. Shared presentation lives in
`frontend/ui.py` and `frontend/assets/retailmetrics.css`; role navigation lives
in `frontend/navigation.py`. Streamlit remains the frontend, and FastAPI
continues to enforce permissions, ownership, validation, and concurrency.

## Experiences

| Audience | Primary work | Presentation |
| --- | --- | --- |
| Admin | Manage the store, people, catalog, and operational queues | Sidebar grouped by overview, operations, administration, analytics, and account; dashboard shortcuts |
| Operations Staff | Fulfill orders and review refunds | Task shortcuts, pending-work metrics, queues, read-only product reference |
| Analyst | Inspect performance and prepare reports | Read-only workspace, blue accent, reporting scope, revenue and traffic charts |
| Customer | Shop, checkout, track orders, manage account | Separate top navigation, warm storefront, product cards, order progress, account sections |

## Visual language

- Ink `#172D32`, staff canvas `#F3F6F6`, white surfaces, borders `#DFE6E5`.
- Staff navigation `#173C40`, operational accent `#176961`, analyst accent `#28679C`.
- Customer canvas `#FAF8F2`, terracotta actions `#BD492E`, warm neutral hero.
- Use native Streamlit controls with visible labels, keyboard focus, and textual status.
- Customer copy describes shopping tasks. Keep implementation and research details in staff evidence pages.
- Product images use contain sizing; missing images use an explicit branded placeholder.
- Product cards grow with content. Do not clip actions inside fixed-height cards.
- Keep destructive actions distinct and retain backend lifecycle restrictions.

## Responsive behavior

The styles cover desktop, tablet (1100px), mobile (768px), and small mobile
(430px). Customer navigation switches to its mobile presentation. Staff retain
the native collapsible sidebar. Content and product columns reflow, tables and
tabs can scroll horizontally, and order summaries stop sticking on mobile.
Both Streamlit column test IDs are supported. Reduced-motion preferences are
respected. Test desktop to mobile to desktop resizing before sign-off.

## Verification

Run `.venv/Scripts/python.exe -m pytest tests/unit` from `RetailMetricsWeb`.
The Streamlit AppTest suite exercises authentication, all staff roles, customer
navigation, cart, checkout, order delivery, refunds, and account sections using
mock API responses. It does not verify browser geometry or live database behavior.

Visual sign-off remains pending for this redesign: the Browser runtime reported
no connected browsers. Inspect real pages at 1440px, 1024px, 768px, and 390px,
including desktop-mobile-desktop resizing, navigation, product cards, cart,
checkout, account forms, tables, and keyboard focus. No live transaction or
database changes are required for the style changes.
