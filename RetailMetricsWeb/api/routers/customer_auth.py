from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.schemas.auth import ForgotPasswordResponse, MessageResponse, TokenResponse
from api.schemas.customer_auth import (
    CustomerChangePasswordRequest,
    CustomerForgotPasswordRequest,
    CustomerLoginRequest,
    CustomerRegisterRequest,
    CustomerResetPasswordRequest,
    CustomerResponse,
)
from core.dependencies import get_customer_auth_service, require_customer
from core.models import CustomerAccount
from services.audit import set_actor, set_entity_id
from services.customer_auth_service import CustomerAuthService


router = APIRouter(prefix="/customer/auth", tags=["Customer authentication"])


@router.post("/register", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def register(request: CustomerRegisterRequest, http_request: Request, service: CustomerAuthService = Depends(get_customer_auth_service)) -> CustomerResponse:
    identity = service.register(
        str(request.email), request.password.get_secret_value(),
        request.first_name, request.last_name, request.phone,
    )
    set_actor(http_request, "customer", identity.account.customer_account_id, "customer")
    set_entity_id(http_request, identity.account.customer_account_id)
    return CustomerResponse.from_identity(identity)


@router.post("/login", response_model=TokenResponse)
def login(request: CustomerLoginRequest, http_request: Request, service: CustomerAuthService = Depends(get_customer_auth_service)) -> TokenResponse:
    try:
        token, expires_in = service.login(str(request.email), request.password.get_secret_value())
    except HTTPException:
        http_request.state.audit_failed_login = True
        raise
    account = service.authenticate_token(token)
    set_actor(http_request, "customer", account.customer_account_id, "customer")
    set_entity_id(http_request, account.customer_account_id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=CustomerResponse)
def me(account: CustomerAccount = Depends(require_customer), service: CustomerAuthService = Depends(get_customer_auth_service)) -> CustomerResponse:
    return CustomerResponse.from_identity(service.identity(account))


@router.post("/logout", response_model=MessageResponse)
def logout(account: CustomerAccount = Depends(require_customer), service: CustomerAuthService = Depends(get_customer_auth_service)) -> MessageResponse:
    service.logout(account)
    return MessageResponse(message="Logged out; existing customer tokens were invalidated.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(request: CustomerChangePasswordRequest, account: CustomerAccount = Depends(require_customer), service: CustomerAuthService = Depends(get_customer_auth_service)) -> MessageResponse:
    service.change_password(account, request.current_password.get_secret_value(), request.new_password.get_secret_value())
    return MessageResponse(message="Password changed; existing customer tokens were invalidated.")


@router.post("/forgot-password", response_model=ForgotPasswordResponse, response_model_exclude_none=True)
def forgot_password(request: CustomerForgotPasswordRequest, service: CustomerAuthService = Depends(get_customer_auth_service)) -> ForgotPasswordResponse:
    token = service.forgot_password(str(request.email))
    return ForgotPasswordResponse(
        message="If the email is registered, password-reset instructions have been sent.",
        reset_token=token,
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(request: CustomerResetPasswordRequest, service: CustomerAuthService = Depends(get_customer_auth_service)) -> MessageResponse:
    service.reset_password(request.reset_token, request.new_password.get_secret_value())
    return MessageResponse(message="Password reset; existing customer tokens were invalidated.")
