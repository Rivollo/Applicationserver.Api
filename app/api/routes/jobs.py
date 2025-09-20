from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
import uuid
import logging
import os
from urllib.parse import urlparse

import httpx
import io
import mimetypes

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.core.config import settings
from app.models.models import Job, JobStatusEnum, Asset, AssetPart
from app.schemas.jobs import CreateJobRequest, JobStatusResponse, CreateJobResponse
from app.utils.envelopes import api_success
from app.services.storage import storage_service

router = APIRouter(tags=["jobs"])


@router.post("/jobs")
def create_job(payload: CreateJobRequest, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    logger = logging.getLogger(__name__)
    image_url = str(payload.imageURL)
    if not image_url.startswith("http"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid imageURL")

    logger.info("Create job requested by user %s for imageURL=%s", user_id, image_url)

    # Create the DB job immediately with status=queued (created)
    job = Job(image_url=image_url, status=JobStatusEnum.queued, created_by=user_id)
    db.add(job)
    db.commit()
    db.refresh(job)

    def _fail_job(error_message: str) -> None:
        try:
            job.status = JobStatusEnum.failed
            job.error_message = error_message
            db.add(job)
            db.commit()
        except Exception:
            logger.exception("Failed to mark job as failed in DB")

    # 1) Download the image from the provided URL (prefer Azure if URL matches our CDN)
    try:
        image_bytes: bytes
        content_type: str
        filename: str
        base = (settings.CDN_BASE_URL or "").rstrip("/")
        if base and image_url.startswith(f"{base}/"):
            image_bytes, ct, filename = storage_service.download_upload_blob_bytes(image_url)
            content_type = ct or "application/octet-stream"
        else:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.get(image_url)
                if resp.status_code != 200:
                    logger.warning("Failed to download image: status=%s url=%s", resp.status_code, image_url)
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to download imageURL")
                image_bytes = resp.content
                content_type = resp.headers.get("content-type", "application/octet-stream")
                parsed = urlparse(image_url)
                filename = os.path.basename(parsed.path) or "image.png"
    except HTTPException as ex:
        _fail_job("Unable to download imageURL")
        raise ex
    except Exception as ex:
        logger.exception("Error downloading image from %s", image_url)
        _fail_job("Unable to download imageURL")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to download imageURL") from ex

    # 2) Send to inference server as multipart/form-data
    inference_url = settings.MODEL_SERVICE_URL if str(settings.MODEL_SERVICE_URL).startswith("http") else "http://74.225.34.67:8081/send"
    form_data = {
        "texture": "true",
        "type": "glb",
        "face_count": "10000",
        "octree_resolution": "128",
        "num_inference_steps": "5",
        "guidance_scale": "5.0",
        "mc_algo": "mc",
    }

    # Improve content-type detection from filename if missing/unknown
    if not content_type or content_type == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            content_type = guessed

    # Validate we actually have content
    if not image_bytes or len(image_bytes) == 0:
        logger.warning("Downloaded image has zero bytes; url=%s filename=%s", image_url, filename)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Downloaded image is empty")

    # Persist a copy to the local Downloads folder and use that file for upload
    try:
        downloads_dir = os.path.expanduser("~/Downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        local_path = os.path.join(downloads_dir, filename)
        if os.path.exists(local_path):
            name, ext = os.path.splitext(filename)
            local_path = os.path.join(downloads_dir, f"{name}-{uuid.uuid4().hex}{ext}")
        with open(local_path, "wb") as out_f:
            out_f.write(image_bytes)
        logger.info("Saved downloaded image to %s (%d bytes, content_type=%s)", local_path, len(image_bytes), content_type)
    except Exception:
        logger.exception("Failed to persist image to Downloads folder")
        _fail_job("Failed to store image locally")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to store image locally")

    # Log the outgoing HTTP request details (without dumping binary content)
    logger.info(
        "Inference HTTP request: POST %s | headers=%s | form_fields=%s | file(name=%s, path=%s, content_type=%s, size_bytes=%d)",
        inference_url,
        {"Accept": "application/json"},
        form_data,
        filename,
        local_path,
        content_type,
        len(image_bytes),
    )

    try:
        with httpx.Client(timeout=httpx.Timeout(120.0)) as client:
            with open(local_path, "rb") as f:
                files = {"image": (filename, f, content_type)}
                req = client.build_request(
                    "POST",
                    inference_url,
                    data=form_data,
                    files=files,
                    headers={"Accept": "application/json"},
                )
                # Log full prepared request headers including multipart boundary
                logger.info("Inference HTTP prepared headers: %s", dict(req.headers))
                r = client.send(req)
            if r.status_code >= 400:
                logger.warning("Inference server error status=%s body=%s", r.status_code, r.text)
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Inference server error")
            data = r.json()
            uid = data.get("uid")
            if not uid:
                logger.warning("Inference server did not return uid: body=%s", r.text)
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid response from inference server")
            logger.info("Inference HTTP response: status=%s uid=%s", r.status_code, uid)
    except HTTPException as ex:
        _fail_job("Inference server error")
        raise ex
    except Exception as ex:
        logger.exception("Error sending image to inference server")
        _fail_job("Inference server error")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Inference server error") from ex

    # 3) Store model job id in physical column (if present) and meta for redundancy
    try:
        model_uuid = uuid.UUID(str(uid))
        logger.info("Parsed provider uid as UUID: raw=%s parsed=%s", uid, model_uuid)
    except Exception:
        model_uuid = uuid.uuid4()
        logger.warning("Provider uid is not a UUID: raw=%s. Generated fallback UUID=%s", uid, model_uuid)
    try:
        job.modelid = model_uuid
        logger.info("Setting job.modelid=%s for job.id=%s", job.modelid, job.id)
    except Exception:
        logger.exception("Failed to set job.modelid for job.id=%s", job.id)
    meta = dict(job.meta or {})
    meta["modelid"] = str(model_uuid)
    job.meta = meta
    job.status = JobStatusEnum.processing
    db.add(job)
    db.commit()
    logger.info("Committed job update: id=%s modelid=%s status=%s", job.id, job.modelid, job.status.value)

    logger.info("Job created id=%s (model_id=%s) for user=%s", job.id, uid, user_id)

    return api_success({"id": str(job.id), "status": job.status.value, "assetId": None})


@router.get("/jobs/{id}")
def get_job(id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	try:
		job_id = uuid.UUID(id)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
	job = db.query(Job).filter(Job.id == job_id, Job.created_by == user_id).one_or_none()
	if job is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

	# If we have a provider model job id, try to poll provider status and update our job
	provider_uid = None
	try:
		provider_uid = str(job.modelid) if getattr(job, "modelid", None) else None
		if not provider_uid:
			provider_uid = (job.meta or {}).get("modelid") if job.meta else None
	except Exception:
		provider_uid = None
	if provider_uid and job.status in (JobStatusEnum.processing, JobStatusEnum.queued):
		logger = logging.getLogger(__name__)
		base = str(settings.MODEL_SERVICE_URL)
		if base.startswith("http"):
			base_root = base.rsplit("/", 1)[0]
		else:
			base_root = "http://74.225.34.67:8081"
		status_urls = [
			f"{base_root}/status/{provider_uid}",
			f"{base_root}/status?uid={provider_uid}",
		]
		resp_json = None
		with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
			for u in status_urls:
				try:
					resp = client.get(u, headers={"Accept": "application/json"})
					if resp.status_code < 400:
						resp_json = resp.json()
						break
				except Exception:
					logger.warning("Provider status request failed for url=%s", u)
		# Interpret provider response
		if isinstance(resp_json, dict):
			provider_status = str(resp_json.get("status", "")).lower()
			if provider_status in ("ready", "completed", "complete", "succeeded", "success", "done") or resp_json.get("parts"):
				# Attempt to extract output URLs
				parts_payload = resp_json.get("parts")
				parts: list[dict] = []
				if isinstance(parts_payload, list) and parts_payload:
					parts = [p for p in parts_payload if isinstance(p, dict)]
				else:
					# Try common single-file keys
					for key in ("fileURL", "url", "download_url", "gltf_url", "glb_url"):
						val = resp_json.get(key)
						if isinstance(val, str) and val:
							parts = [{"id": str(uuid.uuid4()), "name": "model", "fileURL": val}]
							break
				if parts:
					# Create Asset and AssetParts if not already created
					if not job.asset_id:
						asset = Asset(
							title=None,
							source_image_url=job.image_url,
							created_from_job=job.id,
							created_by=job.created_by,
						)
						db.add(asset)
						db.flush()
						position = 0
						for p in parts:
							file_url = p.get("fileURL") or p.get("url")
							name = p.get("name") or "model"
							stored_url = None
							if isinstance(file_url, str) and file_url:
								# Try to download and re-upload to our storage; fallback to provider URL
								try:
									with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
										resp = client.get(file_url)
										if resp.status_code < 400:
											content_type = resp.headers.get("content-type", "application/octet-stream")
											parsed = urlparse(file_url)
											orig_name = os.path.basename(parsed.path) or f"{name}.bin"
											uploaded = storage_service.upload_file_content(user_id=user_id, filename=orig_name, content_type=content_type, stream=io.BytesIO(resp.content))
											stored_url = uploaded
								except Exception:
									stored_url = None
							final_url = stored_url or file_url if isinstance(file_url, str) else None
							if final_url:
								ap = AssetPart(asset_id=asset.id, part_name=name, file_url=final_url, position=position)
								db.add(ap)
								position += 1
						job.asset_id = asset.id
					job.status = JobStatusEnum.ready
					db.add(job)
					db.commit()
			elif provider_status in ("processing", "running", "queued", "pending"):
				if job.status != JobStatusEnum.processing:
					job.status = JobStatusEnum.processing
					db.add(job)
					db.commit()
			elif provider_status in ("failed", "error"):
				job.status = JobStatusEnum.failed
				job.error_message = resp_json.get("error") or resp_json.get("message")
				db.add(job)
				db.commit()

	# If still processing, and provider response indicated processing, just return processing
	file_url_resp: Optional[str] = None
	if job.asset_id:
		# Optionally return first part URL as convenience
		part = db.query(AssetPart).filter(AssetPart.asset_id == job.asset_id).order_by(AssetPart.position.asc()).first()
		if part:
			file_url_resp = part.file_url
	return api_success(JobStatusResponse(id=str(job.id), status=job.status.value, assetId=str(job.asset_id) if job.asset_id else None, fileURL=file_url_resp).model_dump())
