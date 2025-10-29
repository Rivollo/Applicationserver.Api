from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List


class CreateJobRequest(BaseModel):
	imageURL: HttpUrl


class JobStatusResponse(BaseModel):
	id: str
	status: str
	assetId: Optional[str] = None
	glburl: Optional[HttpUrl] = None
	usdzURL: Optional[HttpUrl] = None


class CreateJobResponse(BaseModel):
    jobId: str
    modelJobId: str
    status: str
    assetId: Optional[str] = None


class AssetPart(BaseModel):
	id: str
	name: str
	fileURL: HttpUrl


class AssetResponse(BaseModel):
	id: str
	parts: List[AssetPart]
