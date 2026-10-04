"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import AuthContext, get_current_user
from app.models import Employee, User
from app.schemas import LoginRequest, MeResponse, TokenResponse
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
