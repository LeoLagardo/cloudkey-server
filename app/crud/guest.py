from typing import Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guest import Guest
from app.schemas.reservation import BookerInfoInput, RoomGuestInput


class CRUDGuest:
    async def find_guest(
        self,
        db: AsyncSession,
        organization_id: str,
        guest_id: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Optional[Guest]:
        """Find guest by ID, phone, or email within an organization."""
        if guest_id:
            result = await db.execute(
                select(Guest).where(
                    Guest.id == guest_id,
                    Guest.organization_id == organization_id,
                )
            )
            guest = result.scalar_one_or_none()
            if guest:
                return guest

        conditions = []
        if phone:
            conditions.append(Guest.phone == phone)
        if email:
            conditions.append(Guest.email == email)

        if not conditions:
            return None

        result = await db.execute(
            select(Guest).where(
                Guest.organization_id == organization_id,
                or_(*conditions),
            )
        )
        return result.scalars().first()

    async def create_guest(
        self,
        db: AsyncSession,
        organization_id: str,
        guest_data: BookerInfoInput | RoomGuestInput,
    ) -> Guest:
        """Create a new guest profile."""
        guest_dict = {
            "organization_id": organization_id,
            "first_name": guest_data.first_name,
            "last_name": guest_data.last_name,
            "email": str(guest_data.email) if guest_data.email else None,
            "phone": guest_data.phone,
            "id_type": getattr(guest_data, "id_type", None),
            "id_number": getattr(guest_data, "id_number", None),
            "nationality": getattr(guest_data, "nationality", None),
            "address_line_1": getattr(guest_data, "address_line_1", None),
            "city": getattr(guest_data, "city", None),
            "state": getattr(guest_data, "state", None),
            "country": getattr(guest_data, "country", None),
            "postal_code": getattr(guest_data, "postal_code", None),
            "gstin": getattr(guest_data, "gstin", None),
        }
        guest = Guest(**{k: v for k, v in guest_dict.items() if v is not None or k in ["organization_id", "first_name"]})
        db.add(guest)
        await db.flush()
        return guest

    async def find_or_create(
        self,
        db: AsyncSession,
        organization_id: str,
        guest_data: BookerInfoInput | RoomGuestInput,
    ) -> Guest:
        """Find an existing guest or create a new guest if not found."""
        existing = await self.find_guest(
            db,
            organization_id=organization_id,
            guest_id=guest_data.guest_id,
            phone=guest_data.phone,
            email=str(guest_data.email) if guest_data.email else None,
        )
        if existing:
            # Update fields if provided and not previously set
            updated = False
            for field in ["id_type", "id_number", "nationality", "address_line_1", "city", "state", "country", "postal_code", "gstin"]:
                val = getattr(guest_data, field, None)
                if val and not getattr(existing, field, None):
                    setattr(existing, field, val)
                    updated = True
            if updated:
                await db.flush()
            return existing

        return await self.create_guest(db, organization_id=organization_id, guest_data=guest_data)


crud_guest = CRUDGuest()
