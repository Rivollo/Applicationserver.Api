from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import Upload
from app.schemas.jobs import UploadImageResponse
from app.schemas.uploads import UploadInitRequest, UploadContentResponse
from app.services.storage import storage_service
from app.utils.envelopes import api_success

router = APIRouter(tags=["uploads"])


@router.post("/uploads")
def create_upload(
	payload: UploadInitRequest,
	user_id: str = Depends(get_current_user_id),
	db: Session = Depends(get_db),
):
	filename = payload.filename
	if not filename or "." not in filename or len(filename) > 255:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
	upload_url, file_url = storage_service.create_presigned_upload(user_id=user_id, filename=filename)
	rec = Upload(filename=filename, upload_url=upload_url, file_url=file_url, created_by=user_id)
	db.add(rec)
	db.commit()
	return api_success(UploadImageResponse(uploadUrl=upload_url, fileUrl=file_url).model_dump())


@router.post("/uploads/content")
async def upload_content(
	file: UploadFile = File(...),
	user_id: str = Depends(get_current_user_id),
	db: Session = Depends(get_db),
):
	filename = file.filename
	if not filename or "." not in filename or len(filename) > 255:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
	# Upload stream to Azure Blob (requires Azure env configured)
	file_url = storage_service.upload_file_content(user_id=user_id, filename=filename, content_type=file.content_type, stream=file.file)
	# Persist minimal upload record for audit
	rec = Upload(filename=filename, upload_url=None, file_url=file_url, created_by=user_id)
	db.add(rec)
	db.commit()
	return api_success(UploadContentResponse(fileUrl=file_url).model_dump())
