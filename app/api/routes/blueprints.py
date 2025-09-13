from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import Blueprint
from app.schemas.jobs import BlueprintSummary as BlueprintSummarySchema
from app.utils.envelopes import api_success

router = APIRouter(tags=["blueprints"])


@router.get("/blueprints")
def list_blueprints(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	items = db.query(Blueprint).filter(Blueprint.created_by == user_id).order_by(Blueprint.created_at.desc()).all()
	data = [
		BlueprintSummarySchema(
			id=str(b.id),
			title=b.title,
			status=b.status.value if hasattr(b.status, "value") else str(b.status),
			thumbnailUrl=b.thumbnail_url,
			assetId=str(b.asset_id) if b.asset_id else None,
		).model_dump()
		for b in items
	]
	return api_success(data)


@router.get("/blueprints/{id}")
def get_blueprint(id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	try:
		bp_id = uuid.UUID(id)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint not found")
	b = db.query(Blueprint).filter(Blueprint.id == bp_id, Blueprint.created_by == user_id).one_or_none()
	if b is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blueprint not found")
	resp = BlueprintSummarySchema(
		id=str(b.id),
		title=b.title,
		status=b.status.value if hasattr(b.status, "value") else str(b.status),
		thumbnailUrl=b.thumbnail_url,
		assetId=str(b.asset_id) if b.asset_id else None,
	)
	return api_success(resp.model_dump())
