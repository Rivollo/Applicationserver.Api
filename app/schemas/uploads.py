from pydantic import BaseModel


class UploadInitRequest(BaseModel):
	filename: str
	contentType: str | None = None


class UploadContentResponse(BaseModel):
	fileUrl: str
