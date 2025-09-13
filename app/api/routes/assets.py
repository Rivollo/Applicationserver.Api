from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import Asset, AssetPart
from app.schemas.jobs import AssetResponse, AssetPart as AssetPartSchema
from app.utils.envelopes import api_success

router = APIRouter(tags=["assets"])


@router.get("/assets/{id}")
def get_asset(id: str, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	try:
		asset_id = uuid.UUID(id)
	except ValueError:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
	asset = db.query(Asset).filter(Asset.id == asset_id, Asset.created_by == user_id).one_or_none()
	if asset is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
	parts = db.query(AssetPart).filter(AssetPart.asset_id == asset.id).order_by(AssetPart.position.asc()).all()
	resp = AssetResponse(
		id=str(asset.id),
		parts=[AssetPartSchema(id=str(p.id), name=p.part_name, fileURL=p.file_url) for p in parts],
	)
	return api_success(resp.model_dump())
