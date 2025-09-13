from sqlalchemy import Column, String, Text, Enum, ForeignKey, BigInteger, Integer, JSON, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.models.base import Base


class JobStatusEnum(str, enum.Enum):
	queued = "queued"
	processing = "processing"
	ready = "ready"
	failed = "failed"


class BlueprintStatusEnum(str, enum.Enum):
	processing = "processing"
	ready = "ready"
	failed = "failed"


class User(Base):
	__tablename__ = "users"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	email = Column(Text, nullable=False, unique=True)
	display_name = Column(Text)
	avatar_url = Column(Text)
	created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
	updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Upload(Base):
	__tablename__ = "uploads"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	session_id = Column(Text)
	filename = Column(Text, nullable=False)
	upload_url = Column(Text)
	file_url = Column(Text)
	created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
	created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
	updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
	meta = Column("metadata", JSON, default=dict)


class Job(Base):
	__tablename__ = "jobs"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	image_url = Column(Text, nullable=False)
	status = Column(Enum(JobStatusEnum), nullable=False, default=JobStatusEnum.queued)
	asset_id = Column(UUID(as_uuid=True))
	error_message = Column(Text)
	created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
	created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
	updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
	meta = Column("metadata", JSON, default=dict)


class Asset(Base):
	__tablename__ = "assets"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	title = Column(Text)
	source_image_url = Column(Text)
	created_from_job = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"))
	created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
	created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
	updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
	meta = Column("metadata", JSON, default=dict)


class AssetPart(Base):
	__tablename__ = "asset_parts"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
	part_name = Column(Text, nullable=False)
	file_url = Column(Text, nullable=False)
	mime_type = Column(Text)
	size_bytes = Column(BigInteger)
	position = Column(Integer, default=0)
	created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
	meta = Column("metadata", JSON, default=dict)


class Blueprint(Base):
	__tablename__ = "blueprints"

	id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	title = Column(Text, nullable=False)
	status = Column(Enum(BlueprintStatusEnum), nullable=False, default=BlueprintStatusEnum.processing)
	thumbnail_url = Column(Text)
	asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"))
	created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
	created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
	updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
	meta = Column("metadata", JSON, default=dict)
