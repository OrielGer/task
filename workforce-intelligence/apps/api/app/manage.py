"""Management commands.

Usage:
    python -m app.manage create-superadmin --email you@co.com --password '...'
    # or via env: WFI_ADMIN_EMAIL / WFI_ADMIN_PASSWORD

Used to bootstrap the first SUPER_ADMIN on a fresh production deploy (where
demo seeding is disabled). Idempotent: if the email already exists, it does
nothing.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Role, User
from app.security import hash_password


def create_superadmin(email: str, password: str) -> int:
    if not email or not password:
        print("error: email and password are required", file=sys.stderr)
        return 2
    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            print(f"[manage] user {email} already exists (role={existing.role.value}); no change.")
            return 0
        user = User(
            organization_id=None,  # platform-level
            email=email,
            full_name="Super Admin",
            password_hash=hash_password(password),
            role=Role.SUPER_ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"[manage] created SUPER_ADMIN {email}")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.manage")
    sub = parser.add_subparsers(dest="command", required=True)
    sa = sub.add_parser("create-superadmin", help="Create the first platform SUPER_ADMIN")
    sa.add_argument("--email", default=os.environ.get("WFI_ADMIN_EMAIL", ""))
    sa.add_argument("--password", default=os.environ.get("WFI_ADMIN_PASSWORD", ""))

    args = parser.parse_args(argv)
    if args.command == "create-superadmin":
        return create_superadmin(args.email, args.password)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
