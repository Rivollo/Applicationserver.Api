import uuid
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Optional, BinaryIO

from app.core.config import settings

try:
	from azure.storage.blob import BlobServiceClient, ContentSettings
	from azure.core.credentials import AzureNamedKeyCredential
	_AZURE_AVAILABLE = True
except Exception:
	_AZURE_AVAILABLE = False
	BlobServiceClient = None  # type: ignore
	ContentSettings = None  # type: ignore
	AzureNamedKeyCredential = None  # type: ignore


class StorageService:
	def __init__(self) -> None:
		self._blob_client: Optional[BlobServiceClient] = None

	def _get_blob_service_client(self) -> BlobServiceClient:
		if not _AZURE_AVAILABLE:
			raise RuntimeError("Azure SDK not available. Ensure azure-storage-blob is installed.")
		if self._blob_client is not None:
			return self._blob_client
		if settings.AZURE_STORAGE_CONN_STRING:
			self._blob_client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONN_STRING)
			return self._blob_client
		if settings.AZURE_STORAGE_ACCOUNT and settings.AZURE_STORAGE_KEY:
			account_url = f"https://{settings.AZURE_STORAGE_ACCOUNT}.blob.core.windows.net"
			credential = AzureNamedKeyCredential(settings.AZURE_STORAGE_ACCOUNT, settings.AZURE_STORAGE_KEY)  # type: ignore
			self._blob_client = BlobServiceClient(account_url=account_url, credential=credential)
			return self._blob_client
		raise RuntimeError("Azure Storage is not configured. Set AZURE_STORAGE_CONN_STRING or AZURE_STORAGE_ACCOUNT and AZURE_STORAGE_KEY.")

	def create_presigned_upload(self, user_id: str, filename: str) -> tuple[str, str]:
		upload_id = str(uuid.uuid4())
		blob_path = f"users/{user_id}/uploads/{upload_id}/{quote(filename)}"
		cdn_file_url = f"{settings.CDN_BASE_URL}/{blob_path}"

		# Build a real SAS URL for PUT to the Azure Blob endpoint
		client = self._get_blob_service_client()
		container = settings.STORAGE_CONTAINER_UPLOADS or "uploads"
		blob_client = client.get_blob_client(container=container, blob=blob_path)

		# Generate SAS using SDK helper if available; otherwise raise a clear error
		try:
			from azure.storage.blob import generate_blob_sas, BlobSasPermissions  # type: ignore
		except Exception:
			raise RuntimeError("Azure SDK does not expose SAS helpers. Ensure azure-storage-blob is installed.")

		account_name = client.account_name  # type: ignore
		if settings.AZURE_STORAGE_KEY:
			account_key = settings.AZURE_STORAGE_KEY
		else:
			# When using connection string, pull key from credential if possible
			credential = getattr(client.credential, "account_key", None)  # type: ignore
			if not credential:
				raise RuntimeError("Azure account key not available for SAS generation. Set AZURE_STORAGE_KEY or use a key-bearing connection string.")
			account_key = credential  # type: ignore

		expiry_time = datetime.utcnow() + timedelta(minutes=15)
		sas_token = generate_blob_sas(
			account_name=account_name,
			container_name=container,
			blob_name=blob_path,
			account_key=account_key,
			permission=BlobSasPermissions(write=True, create=True),
			expiry=expiry_time,
		)
		upload_url = f"{blob_client.url}?{sas_token}"
		return upload_url, cdn_file_url

	def asset_part_url(self, user_id: str, blueprint_id: str, asset_id: str, part_id: str, name: str, ext: str) -> str:
		key = f"users/{user_id}/blueprints/{blueprint_id}/asset/{asset_id}/parts/{part_id}-{quote(name)}.{ext}"
		return f"{settings.CDN_BASE_URL}/{key}"

	def blueprint_source_image_url(self, user_id: str, blueprint_id: str, original_filename: str) -> str:
		key = f"users/{user_id}/blueprints/{blueprint_id}/source/{quote(original_filename)}"
		return f"{settings.CDN_BASE_URL}/{key}"

	def upload_file_content(self, user_id: str, filename: str, content_type: Optional[str], stream: BinaryIO) -> str:
		client = self._get_blob_service_client()
		container = settings.STORAGE_CONTAINER_UPLOADS or "uploads"
		upload_id = str(uuid.uuid4())
		blob_path = f"users/{user_id}/uploads/{upload_id}/{quote(filename)}"
		blob_client = client.get_blob_client(container=container, blob=blob_path)
		settings_obj = ContentSettings(content_type=content_type or "application/octet-stream")  # type: ignore
		blob_client.upload_blob(stream, overwrite=True, content_settings=settings_obj)
		return f"{settings.CDN_BASE_URL}/{blob_path}"


storage_service = StorageService()
