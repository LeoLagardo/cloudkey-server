from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.utils.security import get_password_hash


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        normalized = email.strip().lower()
        result = await db.execute(select(User).where(User.email == normalized))
        return result.scalars().first()

    async def create_user(
        self,
        db: AsyncSession,
        *,
        email: str,
        password: str,
        full_name: str,
        phone: Optional[str] = None,
        is_superuser: bool = False,
    ) -> User:
        hashed_password = get_password_hash(password)
        db_user = User(
            email=email.strip().lower(),
            hashed_password=hashed_password,
            full_name=full_name.strip(),
            phone=phone.strip() if phone else None,
            is_active=True,
            is_superuser=is_superuser,
        )
        db.add(db_user)
        await db.flush()
        await db.refresh(db_user)
        return db_user


crud_user = CRUDUser(User)
