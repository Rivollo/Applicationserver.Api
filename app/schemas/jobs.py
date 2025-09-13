from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List


class CreateJobRequest(BaseModel):
	imageURL: HttpUrl


class JobStatusResponse(BaseModel):
	id: str
	status: str
	assetId: Optional[str] = None


class UploadImageResponse(BaseModel):
	uploadUrl: HttpUrl
	fileUrl: HttpUrl


class AssetPart(BaseModel):
	id: str
	name: str
	fileURL: HttpUrl


class AssetResponse(BaseModel):
	id: str
	parts: List[AssetPart]


class BlueprintSummary(BaseModel):
	id: str
	title: str
	status: str
	thumbnailUrl: Optional[HttpUrl] = None
	assetId: Optional[str] = None
