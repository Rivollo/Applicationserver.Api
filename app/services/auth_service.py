"""Authentication service for user signup, login, and OAuth."""

import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import AuthIdentity, AuthProvider, User
from app.services.licensing_service import LicensingService


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    async def create_user(
        db: AsyncSession,
        email: str,
        password: Optional[str] = None,
        name: Optional[str] = None,
        provider: AuthProvider = AuthProvider.EMAIL,
        provider_user_id: Optional[str] = None,
    ) -> User:
        """Create a new user with email/password or OAuth."""
        # Create user
        user = User(
            email=email.lower(),
            password_hash=hash_password(password) if password else None,
            name=name or email.split("@")[0],
        )
        db.add(user)
        await db.flush()

        # Create auth identity
        identity = AuthIdentity(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id or str(user.id),
            email=email.lower(),
        )
        db.add(identity)

        # Create free plan license for user
        await LicensingService.create_free_plan_license(db, user)

        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    async def authenticate_email(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """Authenticate user with email and password."""
        result = await db.execute(
            select(User).where(
                User.email == email.lower(),
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()

        if not user or not user.password_hash:
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(
            select(User).where(
                User.email == email.lower(),
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_google_user(
        db: AsyncSession,
        google_id: str,
        email: str,
        name: Optional[str] = None,
    ) -> User:
        """Get or create user from Google OAuth."""
        # Check if identity exists
        result = await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == AuthProvider.GOOGLE,
                AuthIdentity.provider_user_id == google_id,
            )
        )
        identity = result.scalar_one_or_none()

        if identity:
            # Get existing user
            result = await db.execute(
                select(User).where(User.id == identity.user_id, User.deleted_at.is_(None))
            )
            user = result.scalar_one_or_none()
            if user:
                return user

        # Check if user with email exists
        existing_user = await AuthService.get_user_by_email(db, email)
        if existing_user:
            # Link Google identity to existing user
            identity = AuthIdentity(
                user_id=existing_user.id,
                provider=AuthProvider.GOOGLE,
                provider_user_id=google_id,
                email=email.lower(),
            )
            db.add(identity)
            await db.commit()
            return existing_user

        # Create new user
        return await AuthService.create_user(
            db=db,
            email=email,
            name=name,
            provider=AuthProvider.GOOGLE,
            provider_user_id=google_id,
        )

    @staticmethod
    def generate_token(user_id: uuid.UUID, remember_me: bool = False) -> str:
        """Generate JWT token for user."""
        expires_delta = timedelta(days=30) if remember_me else None
        return create_access_token(
            data={"sub": str(user_id)},
            expires_delta=expires_delta,
        )
