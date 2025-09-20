from pydantic import BaseModel
from typing import Optional, Dict


class UploadInitRequest(BaseModel):
	filename: str
	jobId: Optional[str] = None
	modelId: Optional[str] = None


class UploadContentResponse(BaseModel):
	fileUrl: str
	blobUrl: Optional[str] = None  # Direct blob URL


class DualFormatUploadResponse(BaseModel):
	"""Response for uploads that include both original and converted formats."""
	fileUrl: str  # Primary file URL (usually GLB)
	usdzUrl: Optional[str] = None  # USDZ file URL if converted
	formats: Dict[str, str]  # Dictionary of format -> URL mappings
	blobUrls: Optional[Dict[str, str]] = None  # Dictionary of format -> blob URL mappings
	assetUrl: Optional[str] = None  # Asset URL without extension
	hasMultipleFormats: bool = False  # Whether multiple formats are available
