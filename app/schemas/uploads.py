from pydantic import BaseModel


class UploadInitRequest(BaseModel):
	filename: str


class UploadContentResponse(BaseModel):
	fileUrl: str
