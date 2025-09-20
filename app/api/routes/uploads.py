from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
import uuid
import logging
import os
import io

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import Upload, Job
from app.schemas.jobs import UploadImageResponse
from app.schemas.uploads import UploadInitRequest, UploadContentResponse
from app.services.storage import storage_service
from app.services.model_converter import model_converter
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
	
	logger = logging.getLogger(__name__)
	original_filename = filename
	base_name = os.path.splitext(filename)[0]
	original_extension = os.path.splitext(filename)[1].lstrip('.')
	
	# Check if this is a GLB file that needs conversion to USDZ
	if model_converter.is_glb_file(filename):
		try:
			# Read the original GLB content
			glb_content = await file.read()
			glb_stream = io.BytesIO(glb_content)
			
			# Convert GLB to USDZ
			usdz_bytes, usdz_content_type = model_converter.convert_glb_to_usdz(glb_stream, filename)
			
			# Prepare both files for upload
			files_to_upload = [
				{
					'extension': 'glb',
					'content_type': file.content_type or 'model/gltf-binary',
					'stream': io.BytesIO(glb_content)
				},
				{
					'extension': 'usdz',
					'content_type': usdz_content_type,
					'stream': io.BytesIO(usdz_bytes)
				}
			]
			
			# Upload both files to storage
			cdn_urls, blob_urls, asset_url_base = storage_service.upload_dual_format_files(
				user_id=user_id,
				base_filename=base_name,
				files=files_to_upload
			)
			
			# Create upload records for both files
			glb_url, usdz_url = cdn_urls
			glb_blob_url, usdz_blob_url = blob_urls
			
			# Primary record for GLB file
			glb_rec = Upload(
				filename=f"{base_name}.glb",
				upload_url=None,
				file_url=glb_url,
				created_by=user_id,
				meta={
					"original_filename": original_filename,
					"has_converted_formats": True,
					"converted_formats": ["usdz"],
					"usdz_url": usdz_url,
					"blob_url": glb_blob_url,
					"asset_url_base": asset_url_base
				}
			)
			db.add(glb_rec)
			
			# Secondary record for USDZ file
			usdz_rec = Upload(
				filename=f"{base_name}.usdz",
				upload_url=None,
				file_url=usdz_url,
				created_by=user_id,
				meta={
					"original_filename": original_filename,
					"converted_from": "glb",
					"source_file_url": glb_url,
					"is_converted_format": True,
					"blob_url": usdz_blob_url,
					"asset_url_base": asset_url_base
				}
			)
			db.add(usdz_rec)
			
			db.commit()
			
			logger.info(
				"Successfully uploaded GLB file %s and converted USDZ for user %s. GLB URL: %s, USDZ URL: %s",
				original_filename, user_id, glb_url, usdz_url
			)
			
			# Return both URLs in the response
			return api_success({
				"fileUrl": glb_url,  # Primary GLB file URL
				"usdzUrl": usdz_url,  # Converted USDZ file URL
				"formats": {
					"glb": glb_url,
					"usdz": usdz_url
				},
				"blobUrls": {
					"glb": glb_blob_url,
					"usdz": usdz_blob_url
				},
				"assetUrl": asset_url_base,  # Asset URL without extension
				"hasMultipleFormats": True
			})
			
		except Exception as e:
			logger.error(
				"Failed to convert GLB file %s to USDZ for user %s: %s",
				original_filename, user_id, str(e)
			)
			# Fall back to uploading only the original GLB file
			file.file.seek(0)  # Reset file pointer
			file_url, blob_url = storage_service.upload_file_content(
				user_id=user_id,
				filename=filename,
				content_type=file.content_type,
				stream=file.file
			)
			
			# Create upload record with conversion failure info
			rec = Upload(
				filename=filename,
				upload_url=None,
				file_url=file_url,
				created_by=user_id,
				meta={
					"conversion_attempted": True,
					"conversion_failed": True,
					"conversion_error": str(e),
					"blob_url": blob_url
				}
			)
			db.add(rec)
			db.commit()
			
			return api_success(UploadContentResponse(fileUrl=file_url, blobUrl=blob_url).model_dump())
	else:
		# Handle non-GLB files normally
		file_url, blob_url = storage_service.upload_file_content(
			user_id=user_id,
			filename=filename,
			content_type=file.content_type,
			stream=file.file
		)
		
		# Persist minimal upload record for audit
		rec = Upload(
			filename=filename, 
			upload_url=None, 
			file_url=file_url, 
			created_by=user_id,
			meta={"blob_url": blob_url}
		)
		db.add(rec)
		db.commit()
		
		return api_success(UploadContentResponse(fileUrl=file_url, blobUrl=blob_url).model_dump())
