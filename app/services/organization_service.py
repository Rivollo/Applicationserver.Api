"""Organization provisioning helpers.

Creates a personal organization for a user on-demand so routes don't need
to hard-fail when the user has no org membership yet.
"""

import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Organization, OrgMember, OrgRole


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100]


class OrganizationService:
    @staticmethod
    async def get_or_create_org_id(
        db: AsyncSession, user_id: uuid.UUID, user_name_or_email: Optional[str] = None
    ) -> uuid.UUID:
        # Try existing membership
        res = await db.execute(
            select(OrgMember.org_id).where(OrgMember.user_id == user_id).limit(1)
        )
        org_id = res.scalar_one_or_none()
        if org_id:
            return org_id

        # Create a personal org
        base_name = user_name_or_email or "personal"
        base_slug = _slugify(base_name) or "user"

        org = Organization(name=f"{base_name}", slug=base_slug, created_by=user_id)
        db.add(org)
        await db.flush()  # get org.id

        # Ensure slug uniqueness by appending suffix if needed (best-effort)
        # Note: relying on DB constraint if collision happens; not critical here

        member = OrgMember(org_id=org.id, user_id=user_id, role=OrgRole.OWNER, created_by=user_id)
        db.add(member)
        await db.commit()

        return org.id

