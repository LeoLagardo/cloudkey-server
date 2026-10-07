import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation import DocumentSequence
from app.models.property_settings import PropertySettings
from app.utils.enums import DocType, InvoiceType


class SequenceService:
    async def get_next_number(
        self,
        db: AsyncSession,
        property_id: str,
        doc_type: str,
        period_key: Optional[str] = None,
    ) -> int:
        """
        Atomically increment and return the next sequential number for a property and document type.
        """
        if not period_key:
            period_key = datetime.now(timezone.utc).strftime("%Y")

        stmt = (
            select(DocumentSequence)
            .where(
                DocumentSequence.property_id == property_id,
                DocumentSequence.doc_type == doc_type,
                DocumentSequence.period_key == period_key,
            )
            .with_for_update()
        )
        result = await db.execute(stmt)
        seq = result.scalar_one_or_none()

        if not seq:
            seq = DocumentSequence(
                id=str(uuid.uuid4()),
                property_id=property_id,
                doc_type=doc_type,
                period_key=period_key,
                last_number=1,
            )
            db.add(seq)
            await db.flush()
            return 1

        seq.last_number += 1
        await db.flush()
        return seq.last_number

    async def generate_invoice_number(
        self,
        db: AsyncSession,
        property_id: str,
        invoice_type: str = InvoiceType.TAX_INVOICE.value,
        custom_prefix: Optional[str] = None,
    ) -> str:
        """
        Generate sequential document number formatted as:
        {PREFIX}{PERIOD}-{NUMBER:05d}
        e.g. INV-2026-00001 or CN-2026-00001 or PRO-2026-00001
        """
        period_key = datetime.now(timezone.utc).strftime("%Y")

        if invoice_type == InvoiceType.CREDIT_NOTE.value:
            doc_type = DocType.CREDIT_NOTE.value
            prefix = "CN-"
        elif invoice_type == InvoiceType.PROFORMA.value:
            doc_type = "PROFORMA"
            prefix = "PRO-"
        else:
            doc_type = DocType.INVOICE.value
            if custom_prefix:
                prefix = custom_prefix if (custom_prefix.endswith("-") or custom_prefix.endswith("/")) else f"{custom_prefix}-"
            else:
                # Check property settings
                prop_settings_res = await db.execute(
                    select(PropertySettings.invoice_prefix).where(
                        PropertySettings.property_id == property_id
                    )
                )
                pref = prop_settings_res.scalar_one_or_none()
                if pref:
                    prefix = pref if (pref.endswith("-") or pref.endswith("/")) else f"{pref}-"
                else:
                    prefix = "INV-"

        next_num = await self.get_next_number(
            db,
            property_id=property_id,
            doc_type=doc_type,
            period_key=period_key,
        )

        return f"{prefix}{period_key}-{next_num:05d}"


sequence_service = SequenceService()
