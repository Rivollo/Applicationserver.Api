from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class UploadInitRequest(BaseModel):
	filename: str = Field(..., min_length=1, max_length=255)
	job_id: Optional[str] = Field(default=None, alias="jobId")
	model_id: Optional[str] = Field(default=None, alias="modelId")

	class Config:
		populate_by_name = True

	@field_validator("filename")
	@classmethod
	def _validate_filename(cls, value: str) -> str:
		if "." not in value:
			raise ValueError("Filename must include an extension")
		return value


class UploadInitResponse(BaseModel):
	upload_id: str = Field(..., alias="uploadId")
	upload_url: HttpUrl = Field(..., alias="uploadURL")
	expires_at: datetime = Field(..., alias="expiresAt")
	image_url: Optional[HttpUrl] = Field(default=None, alias="imageURL")

	class Config:
		populate_by_name = True


class UploadContentResponse(BaseModel):
	upload_id: str = Field(..., alias="uploadId")
	url: HttpUrl
	image_url: Optional[HttpUrl] = Field(default=None, alias="imageURL")
	public_url: Optional[HttpUrl] = Field(default=None, alias="publicURL")
	content_type: Optional[str] = Field(default=None, alias="contentType")
	size_bytes: int = Field(..., alias="sizeBytes", ge=0)
	formats: Optional[Dict[str, str]] = None
	blob_urls: Optional[Dict[str, str]] = Field(default=None, alias="blobUrls")

	class Config:
		populate_by_name = True


class BackgroundRemovalRequest(BaseModel):
	image_url: HttpUrl = Field(..., alias="imageURL")
	refine_edges: bool = Field(default=False, alias="refineEdges")
	restore_shadow: bool = Field(default=False, alias="restoreShadow")

	class Config:
		populate_by_name = True


class BackgroundRemovalResponse(BaseModel):
	original_image_url: HttpUrl = Field(..., alias="originalImageURL")
	cleaned_image_url: HttpUrl = Field(..., alias="cleanedImageURL")
	mask_url: Optional[HttpUrl] = Field(default=None, alias="maskURL")
	quality_score: Optional[float] = Field(default=1.0, alias="qualityScore", ge=0.0, le=1.0)

	class Config:
		populate_by_name = True


class DualFormatUploadResponse(BaseModel):
	"""Response for uploads that include both original and converted formats."""

	file_url: str
	usdz_url: Optional[str] = None
	formats: Dict[str, str]
	blob_urls: Optional[Dict[str, str]] = None
	asset_url: Optional[str] = None
	has_multiple_formats: bool = False
