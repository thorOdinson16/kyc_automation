"""Seed default applicant, reviewer and admin accounts.

Run from the ``backend`` directory:

    python -m scripts.seed_users
"""
import asyncio

from sqlalchemy import select

from app.core.security import security
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole

DEFAULT_USERS = [
    ("Applicant", "applicant@kyc.ai", "applicant123", UserRole.APPLICANT),
    ("Reviewer", "reviewer@kyc.ai", "review123", UserRole.REVIEWER),
    ("Admin", "admin@kyc.ai", "admin123", UserRole.ADMIN),
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        for name, email, password, role in DEFAULT_USERS:
            existing = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing:
                print(f"skip   {email} ({role.value}) already exists")
                continue

            db.add(
                User(
                    name=name,
                    email=email,
                    password_hash=security.hash_password(password),
                    role=role,
                )
            )
            print(f"create {email} ({role.value})")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
