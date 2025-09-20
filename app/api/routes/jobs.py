from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
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

	# If we have a provider model job id, get status from inference server and return as-is
	provider_uid = str(job.modelid) if getattr(job, "modelid", None) else None
	logger = logging.getLogger(__name__)
	logger.info("GET /jobs/%s: job.modelid=%s, provider_uid=%s", id, getattr(job, "modelid", None), provider_uid)
	
	if provider_uid:
		# Use the exact inference server URL format as specified
		inference_url = f"http://74.225.34.67:8081/status/{provider_uid}"
		logger.info("Querying inference server: %s", inference_url)
		
		try:
			with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
				resp = client.get(inference_url)
				logger.info("Inference server response: status=%s, content-type=%s", resp.status_code, resp.headers.get("content-type", "unknown"))
				
				if resp.status_code < 400:
					# Check if response is JSON or binary
					content_type = resp.headers.get("content-type", "").lower()
					
					if "application/json" in content_type or "text/" in content_type:
						# Try to parse as JSON
						try:
							return resp.json()
						except Exception as json_error:
							logger.warning("Failed to parse response as JSON: %s", str(json_error))
							# Return raw text if JSON parsing fails
							return {"raw_response": resp.text}
					else:
						# Binary response - return it as-is with proper headers
						return Response(
							content=resp.content,
							media_type=content_type or "application/octet-stream",
							headers=dict(resp.headers)
						)
				else:
					logger.warning("Inference server returned error status: %s", resp.status_code)
		except Exception as e:
			logger.warning("Provider status request failed for url=%s: %s", inference_url, str(e))

	# If no provider UID or all requests failed, return basic job status as raw JSON
	logger.info("Returning fallback response for job %s", id)
	return {"id": str(job.id), "status": job.status.value, "assetId": None, "fileURL": None}
