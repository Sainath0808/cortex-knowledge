"""Seed script: creates an admin user and a demo member.

Usage: python scripts/seed.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.core.security import hash_password  # noqa: E402
from app.db.models import UserRole  # noqa: E402
from app.db.repositories.users import UserRepository  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402

USERS = [
    ("admin@cortex.local", "admin-password-123", UserRole.admin),
    ("demo@cortex.local", "demo-password-123", UserRole.member),
]


async def main() -> None:
    async with async_session_factory() as session:
        repo = UserRepository(session)
        for email, password, role in USERS:
            if await repo.get_by_email(email):
                print(f"exists: {email}")
                continue
            await repo.create(email=email, hashed_password=hash_password(password), role=role)
            print(f"created: {email} ({role.value})")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
