from pydantic import BaseModel
from typing import Optional


class UploadInitRequest(BaseModel):
	filename: str
	jobId: Optional[str] = None
	modelId: Optional[str] = None


class UploadContentResponse(BaseModel):
	fileUrl: str
