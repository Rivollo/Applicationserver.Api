import uuid
from typing import Dict, List

from app.core.config import settings


class ModelServiceClient:
	def submit_job(self, image_url: str) -> str:
		# Returns a provider-side task id (simulated)
		return str(uuid.uuid4())

	def get_result(self, task_id: str) -> Dict:
		# Simulate a ready result immediately for mock
		asset_id = str(uuid.uuid4())
		parts: List[Dict] = [
			{"id": str(uuid.uuid4()), "name": "geometry", "fileURL": f"{settings.CDN_BASE_URL}/assets/{asset_id}/geometry.glb"},
			{"id": str(uuid.uuid4()), "name": "texture", "fileURL": f"{settings.CDN_BASE_URL}/assets/{asset_id}/texture.jpg"},
		]
		return {"asset_id": asset_id, "parts": parts}


model_service = ModelServiceClient()
