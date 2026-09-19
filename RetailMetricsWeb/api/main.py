from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routers.auth import router as auth_router
from api.routers.business import router as business_router
from api.routers.admin_users import router as admin_users_router
from api.routers.admin_customers import router as admin_customers_router
from api.routers.customer_auth import router as customer_auth_router
from api.routers.customer_profile import router as customer_profile_router
from api.routers.customer_resources import router as customer_resources_router
from api.routers.storefront import router as storefront_router
from api.routers.checkout import router as checkout_router
from api.routers.refund_workflow import router as refund_workflow_router
from api.routers.order_workflow import router as order_workflow_router
from api.routers.analytics import router as analytics_router
from api.routers.notifications import router as notifications_router
from api.routers.audit import router as audit_router
from core.config import get_settings
from db.connection import close_pool, initialize_pool


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_pool(get_settings())
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="RetailMetricsWeb API",
    version="1.0.0",
    description="RetailMetrics staff/customer authentication, management, CRUD, and UI API.",
    lifespan=lifespan,
)
app.include_router(auth_router)
app.include_router(business_router)
app.include_router(admin_users_router)
app.include_router(customer_auth_router)
app.include_router(customer_profile_router)
app.include_router(customer_resources_router)
app.include_router(storefront_router)
app.include_router(checkout_router)
app.include_router(refund_workflow_router)
app.include_router(order_workflow_router)
app.include_router(admin_customers_router)
app.include_router(analytics_router)
app.include_router(notifications_router)
app.include_router(audit_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
