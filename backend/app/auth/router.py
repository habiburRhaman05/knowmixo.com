from fastapi import APIRouter, Depends, Header, HTTPException

from app.auth import service
from app.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GenericAccepted,
    GoogleAuthRequest,
    LoginRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from app.auth.service import AuthError, SessionPrincipal
from app.db import connection
from app.deps import get_current_principal
from app.security.google_oauth import GoogleTokenError, verify_google_id_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _raise(exc: AuthError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post("/signup", status_code=202, response_model=GenericAccepted)
def signup(body: SignupRequest):
    with connection() as conn:
        service.signup(conn, body.email, body.password, body.name)
    return GenericAccepted(status="verify_email_sent")


@router.post("/login")
def login(body: LoginRequest):
    try:
        with connection() as conn:
            token = service.login_with_password(conn, body.email, body.password)
    except AuthError as exc:
        _raise(exc)
    return {"session_token": token}


@router.post("/google")
def google_login(body: GoogleAuthRequest):
    try:
        claims = verify_google_id_token(body.id_token)
    except GoogleTokenError as exc:
        raise HTTPException(status_code=401, detail={"code": "invalid_google_token", "message": str(exc)})

    try:
        with connection() as conn:
            token = service.login_or_signup_with_google(conn, claims)
    except AuthError as exc:
        _raise(exc)
    return {"session_token": token}


@router.post("/verify-email", response_model=GenericAccepted)
def verify_email(body: VerifyEmailRequest):
    try:
        with connection() as conn:
            service.verify_email(conn, body.token)
    except AuthError as exc:
        _raise(exc)
    return GenericAccepted()


@router.post("/resend-verification", status_code=202, response_model=GenericAccepted)
def resend_verification(body: ResendVerificationRequest):
    with connection() as conn:
        service.resend_verification(conn, body.email)
    return GenericAccepted()


@router.post("/forgot-password", status_code=202, response_model=GenericAccepted)
def forgot_password(body: ForgotPasswordRequest):
    with connection() as conn:
        service.forgot_password(conn, body.email)
    return GenericAccepted()


@router.post("/reset-password", response_model=GenericAccepted)
def reset_password(body: ResetPasswordRequest):
    try:
        with connection() as conn:
            service.reset_password(conn, body.token, body.new_password)
    except AuthError as exc:
        _raise(exc)
    return GenericAccepted()


@router.post("/change-password", response_model=GenericAccepted)
def change_password(body: ChangePasswordRequest, principal: SessionPrincipal = Depends(get_current_principal)):
    try:
        with connection() as conn:
            service.change_password(conn, principal.user_id, body.current_password, body.new_password)
    except AuthError as exc:
        _raise(exc)
    return GenericAccepted()


@router.post("/logout", status_code=204)
def logout(authorization: str = Header()):
    token = authorization.removeprefix("Bearer ").strip()
    with connection() as conn:
        service.revoke_session(conn, token)
    return None


@router.post("/logout-all", status_code=204)
def logout_all(principal: SessionPrincipal = Depends(get_current_principal)):
    with connection() as conn:
        service.revoke_all_sessions(conn, principal.user_id)
    return None
