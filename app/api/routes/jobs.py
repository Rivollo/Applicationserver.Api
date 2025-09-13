from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import Job, JobStatusEnum, Asset, AssetPart, Blueprint, BlueprintStatusEnum
from app.schemas.jobs import CreateJobRequest, JobStatusResponse
from app.services.model_service import model_service
from app.services.storage import storage_service
from app.utils.envelopes import api_success

router = APIRouter(tags=["jobs"])


@router.post("/jobs")
def create_job(payload: CreateJobRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	if not str(payload.imageURL).startswith("http"):
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid imageURL")

	job = Job(image_url=str(payload.imageURL), status=JobStatusEnum.queued, created_by=user_id)
	db.add(job)
	db.commit()
	db.refresh(job)

	provider_task_id = model_service.submit_job(job.image_url)
	result = model_service.get_result(provider_task_id)

	# Create asset and blueprint grouped under the user
	asset_uuid = uuid.UUID(result["asset_id"])
	asset = Asset(id=asset_uuid, source_image_url=job.image_url, created_from_job=job.id, created_by=user_id)
	db.add(asset)

	blueprint = Blueprint(title=f"Blueprint {asset_uuid.hex[:8]}", status=BlueprintStatusEnum.ready, asset_id=asset.id, created_by=user_id)
	db.add(blueprint)
	db.flush()

	for p in result["parts"]:
		part_id = uuid.uuid4()
		ext = p["fileURL"].split(".")[-1]
		file_url = storage_service.asset_part_url(user_id=user_id, blueprint_id=str(blueprint.id), asset_id=str(asset.id), part_id=str(part_id), name=p["name"], ext=ext)
		part = AssetPart(id=part_id, asset_id=asset.id, part_name=p["name"], file_url=file_url)
		db.add(part)

	db.flush()
	job.status = JobStatusEnum.ready
	job.asset_id = asset.id
	db.commit()

	return api_success(JobStatusResponse(id=str(job.id), status=job.status.value, assetId=str(job.asset_id)).model_dump())


@router.get("/jobs/{id}")
def get_job(id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	try:
		job_id = uuid.UUID(id)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
	job = db.query(Job).filter(Job.id == job_id, Job.created_by == user_id).one_or_none()
	if job is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
	return api_success(JobStatusResponse(id=str(job.id), status=job.status.value, assetId=str(job.asset_id) if job.asset_id else None).model_dump())
