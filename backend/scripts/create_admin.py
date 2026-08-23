"""Create or promote a local administrator without relying on a running API."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os

from sqlalchemy import select

from app.auth import get_password_hash
from app.database import AsyncSessionLocal
from app.models_db import User


async def create_admin(email: str, password: str) -> str:
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if row is None:
            row = User(email=email, password_hash=get_password_hash(password), role="admin")
            session.add(row)
            action = "created"
        else:
            row.password_hash = get_password_hash(password)
            row.role = "admin"
            row.session_version = int(row.session_version or 1) + 1
            action = "updated"
        await session.commit()
        return action


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD") or getpass.getpass("Admin password: ")
    if len(password) < 10:
        raise SystemExit("password must contain at least 10 characters")
    action = asyncio.run(create_admin(args.email.strip().lower(), password))
    print(f"admin {action}: {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
