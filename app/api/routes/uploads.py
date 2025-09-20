from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import Upload, Job
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

	# If jobId is provided, and a modelId is provided, persist modelId on the job (both column and meta)
	if getattr(payload, "jobId", None):
		try:
			job_uuid = uuid.UUID(payload.jobId)
		except Exception:
			job_uuid = None
		if job_uuid is not None:
			job = db.query(Job).filter(Job.id == job_uuid, Job.created_by == user_id).one_or_none()
			if job is not None and getattr(payload, "modelId", None):
				meta = dict(job.meta or {})
				model_uuid = uuid.UUID(str(payload.modelId))
				try:
					job.modelid = model_uuid
					logging.getLogger(__name__).info("uploads: set job.modelid=%s for job.id=%s", job.modelid, job.id)
				except Exception:
					logging.getLogger(__name__).exception("uploads: failed setting job.modelid for job.id=%s", job.id)
				meta["modelid"] = str(model_uuid)
				job.meta = meta
				db.add(job)
				# Best-effort commit of job update
				try:
					db.commit()
				except Exception:
					pass
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
