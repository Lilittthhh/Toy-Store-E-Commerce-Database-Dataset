from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg2.extensions import connection

from core.config import Settings, get_settings
from core.models import AppUser, CustomerAccount, Role
from db.connection import get_db_connection
from repositories.user_repository import PostgresUserRepository, UserRepository
from repositories.business_repository import BusinessRepository
from services.auth_service import AuthService
from services.business_service import BusinessService
from services.admin_user_service import AdminUserService
from repositories.customer_repository import CustomerRepository, PostgresCustomerRepository
from services.admin_customer_service import AdminCustomerService
from services.customer_auth_service import CustomerAuthService
from repositories.customer_resource_repository import CustomerResourceRepository, PostgresCustomerResourceRepository
from services.customer_resource_service import CustomerResourceService
from repositories.storefront_repository import PostgresStorefrontRepository, StorefrontRepository
from services.storefront_service import StorefrontService
from repositories.checkout_repository import CheckoutRepository, PostgresCheckoutRepository
from services.checkout_service import CheckoutService
from repositories.refund_workflow_repository import (
    PostgresRefundWorkflowRepository,
    RefundWorkflowRepository,
)
from services.refund_workflow_service import RefundWorkflowService
from repositories.order_workflow_repository import (
    OrderWorkflowRepository,
    PostgresOrderWorkflowRepository,
)
from services.order_workflow_service import OrderWorkflowService
from repositories.analytics_repository import AnalyticsRepository, PostgresAnalyticsRepository
from services.analytics_service import AnalyticsService
from services.notifications.outbox import NotificationOutbox


bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository(
    conn: connection = Depends(get_db_connection),
) -> UserRepository:
    return PostgresUserRepository(conn)


def get_auth_service(
    request: Request,
    repository: UserRepository = Depends(get_user_repository),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    def queue(message) -> None:
        if not hasattr(request.state, "post_commit_notification_messages"):
            request.state.post_commit_notification_messages = []
        request.state.post_commit_notification_messages.append(message)

    return AuthService(repository, settings, queue)


def get_business_repository(
    conn: connection = Depends(get_db_connection),
) -> BusinessRepository:
    return BusinessRepository(conn)


def get_business_service(
    repository: BusinessRepository = Depends(get_business_repository),
) -> BusinessService:
    return BusinessService(repository)


def get_admin_user_service(
    repository: UserRepository = Depends(get_user_repository),
) -> AdminUserService:
    return AdminUserService(repository)


def get_customer_repository(
    conn: connection = Depends(get_db_connection),
) -> CustomerRepository:
    return PostgresCustomerRepository(conn)


def get_customer_auth_service(
    request: Request,
    repository: CustomerRepository = Depends(get_customer_repository),
    settings: Settings = Depends(get_settings),
) -> CustomerAuthService:
    def queue(message) -> None:
        if not hasattr(request.state, "post_commit_notification_messages"):
            request.state.post_commit_notification_messages = []
        request.state.post_commit_notification_messages.append(message)

    return CustomerAuthService(repository, settings, queue)


def get_admin_customer_service(
    repository: CustomerRepository = Depends(get_customer_repository),
) -> AdminCustomerService:
    return AdminCustomerService(repository)


def get_customer_resource_repository(
    conn: connection = Depends(get_db_connection),
) -> CustomerResourceRepository:
    return PostgresCustomerResourceRepository(conn)


def get_customer_resource_service(
    repository: CustomerResourceRepository = Depends(get_customer_resource_repository),
) -> CustomerResourceService:
    return CustomerResourceService(repository)


def get_storefront_repository(
    conn: connection = Depends(get_db_connection),
) -> StorefrontRepository:
    return PostgresStorefrontRepository(conn)


def get_storefront_service(
    repository: StorefrontRepository = Depends(get_storefront_repository),
) -> StorefrontService:
    return StorefrontService(repository)


def get_notification_outbox(
    request: Request,
    conn: connection = Depends(get_db_connection),
) -> NotificationOutbox:
    if not hasattr(request.state, "notification_ids"):
        request.state.notification_ids = []
    return NotificationOutbox(conn, request.state.notification_ids)


def get_checkout_repository(
    conn: connection = Depends(get_db_connection),
) -> CheckoutRepository:
    return PostgresCheckoutRepository(conn)


def get_checkout_service(
    repository: CheckoutRepository = Depends(get_checkout_repository),
    outbox: NotificationOutbox = Depends(get_notification_outbox),
) -> CheckoutService:
    return CheckoutService(repository, outbox)


def get_refund_workflow_repository(
    conn: connection = Depends(get_db_connection),
) -> RefundWorkflowRepository:
    return PostgresRefundWorkflowRepository(conn)


def get_refund_workflow_service(
    repository: RefundWorkflowRepository = Depends(get_refund_workflow_repository),
    outbox: NotificationOutbox = Depends(get_notification_outbox),
) -> RefundWorkflowService:
    return RefundWorkflowService(repository, outbox)


def get_order_workflow_repository(
    conn: connection = Depends(get_db_connection),
) -> OrderWorkflowRepository:
    return PostgresOrderWorkflowRepository(conn)


def get_order_workflow_service(
    repository: OrderWorkflowRepository = Depends(get_order_workflow_repository),
    outbox: NotificationOutbox = Depends(get_notification_outbox),
) -> OrderWorkflowService:
    return OrderWorkflowService(repository, outbox)


def get_analytics_repository(conn: connection = Depends(get_db_connection)) -> AnalyticsRepository:
    return PostgresAnalyticsRepository(conn)


def get_analytics_service(repository: AnalyticsRepository = Depends(get_analytics_repository)) -> AnalyticsService:
    return AnalyticsService(repository)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: AuthService = Depends(get_auth_service),
) -> AppUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = service.authenticate_token(credentials.credentials)
    from services.audit import set_actor
    set_actor(request, "staff", user.app_user_id, user.role.value)
    return user


def require_customer(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: CustomerAuthService = Depends(get_customer_auth_service),
) -> CustomerAccount:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer bearer authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    customer = service.authenticate_token(credentials.credentials)
    from services.audit import set_actor
    set_actor(request, "customer", customer.customer_account_id, "customer")
    return customer


def require_roles(*allowed_roles: Role) -> Callable[..., AppUser]:
    allowed = frozenset(allowed_roles)

    def role_dependency(user: AppUser = Depends(get_current_user)) -> AppUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The current role is not authorized for this operation.",
            )
        return user

    return role_dependency
