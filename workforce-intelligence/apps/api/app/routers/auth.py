"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import get_settings
from app.db import get_db
from app.deps import AuthContext, get_current_user
from app.models import Employee, User
from app.schemas import (
    AuthOptionsOut,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    TokenResponse,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/options", response_model=AuthOptionsOut)
def options() -> AuthOptionsOut:
    """Login-page options. Demo shortcuts are offered only when the demo accounts
    are actually seeded (SEED_DEMO), so production never advertises them."""
    return AuthOptionsOut(demo_logins=get_settings().seed_demo)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(
        select(User).where(User.email == body.email)
    ).scalar_one_or_none()
    # Constant-ish response: verify even if user is None to reduce enumeration.
    if user is None or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(
        user_id=user.id, organization_id=user.organization_id, role=user.role.value
    )
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        organization_id=user.organization_id,
        user_id=user.id,
    )


@router.get("/me", response_model=MeResponse)
def me(ctx: AuthContext = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    employee_id = None
    emp = db.execute(
        select(Employee).where(Employee.user_id == ctx.user_id)
    ).scalar_one_or_none()
    if emp is not None:
        employee_id = emp.id
    return MeResponse(
        user_id=ctx.user.id,
        email=ctx.user.email,
        full_name=ctx.user.full_name,
        role=ctx.role.value,
        organization_id=ctx.organization_id,
        employee_id=employee_id,
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    ctx: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Change the signed-in user's own password.

    A wrong current password is a 400, not a 401: the dashboard treats 401 as an
    expired session and signs the user out.
    """
    user = ctx.user
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "New password must be different from the current one"
        )
    user.password_hash = hash_password(body.new_password)
    db.commit()
    record_audit(
        db, organization_id=user.organization_id, viewer_user_id=user.id, employee_id=None,
        action="change_password", resource_type="user", resource_id=user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
