from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from core.dependencies import get_auth_service, get_current_user
from core.models import AppUser
from services.audit import set_actor, set_entity_id
from services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    http_request: Request,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    user = service.register(
        username=request.username,
        email=str(request.email),
        password=request.password.get_secret_value(),
    )
    set_actor(http_request, "staff", user.app_user_id, user.role.value)
    set_entity_id(http_request, user.app_user_id)
    return UserResponse.from_user(user)


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    http_request: Request,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        token, expires_in = service.login(
            identifier=request.identifier,
            password=request.password.get_secret_value(),
        )
    except HTTPException:
        http_request.state.audit_failed_login = True
        raise
    user = service.authenticate_token(token)
    set_actor(http_request, "staff", user.app_user_id, user.role.value)
    set_entity_id(http_request, user.app_user_id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout", response_model=MessageResponse)
def logout(
    current_user: AppUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.logout(current_user)
    return MessageResponse(message="Logged out; existing tokens were invalidated.")


@router.get("/me", response_model=UserResponse)
def current_user(user: AppUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_user(user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: AppUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.change_password(
        current_user,
        current_password=request.current_password.get_secret_value(),
        new_password=request.new_password.get_secret_value(),
    )
    return MessageResponse(
        message="Password changed; existing tokens were invalidated."
    )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    response_model_exclude_none=True,
)
def forgot_password(
    request: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> ForgotPasswordResponse:
    reset_token = service.forgot_password(str(request.email))
    return ForgotPasswordResponse(
        message=(
            "If the email is registered, password-reset instructions have been sent."
        ),
        reset_token=reset_token,
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    request: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    service.reset_password(
        reset_token=request.reset_token,
        new_password=request.new_password.get_secret_value(),
    )
    return MessageResponse(
        message="Password reset; existing tokens were invalidated."
    )
