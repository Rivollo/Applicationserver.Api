import io
import logging
import os
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

from azure.storage.blob import ContentSettings
from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from withoutbg import WithoutBG

from app.models.models import Product, ProductAsset, ProductAssetMapping
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


class BackgroundRemovalService:
    """Background removal + blob + DB persistence."""

    def __init__(self) -> None:
        self._withoutbg_model: Optional[WithoutBG] = None
        self._initialization_attempted = False

    def _ensure_utf8_environment(self) -> None:
        """Ensure UTF-8 encoding is set for the current process and subprocesses."""
        if os.name != "nt":
            return

        os.environ["PYTHONIOENCODING"] = "utf-8"
        os.environ["PYTHONUTF8"] = "1"

        try:
            import subprocess

            subprocess.run(["chcp", "65001"], shell=True, capture_output=True, check=False)
        except Exception:
            pass

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    def _get_withoutbg_model(self) -> WithoutBG:
        """Return a singleton instance of the background removal model."""
        if self._withoutbg_model is None and not self._initialization_attempted:
            self._initialization_attempted = True
            self._ensure_utf8_environment()

            cache_dir = (
                Path(os.getenv("LOCALAPPDATA", os.getcwd())) / "withoutbg_cache"
                if os.name == "nt"
                else Path(os.getenv("HOME", "/tmp")) / "withoutbg_cache"
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["WITHOUTBG_CACHE"] = str(cache_dir)

            hf_cache = cache_dir / "huggingface"
            hf_cache.mkdir(parents=True, exist_ok=True)
            os.environ["HF_HOME"] = str(hf_cache)

            hf_hub_cache = hf_cache / "hub"
            hf_hub_cache.mkdir(parents=True, exist_ok=True)
            os.environ["HF_HUB_CACHE"] = str(hf_hub_cache)

            try:
                logging.info("Initializing WithoutBG model with cache directory: %s", cache_dir)
                try:
                    with open(os.devnull, "w", encoding="utf-8") as devnull:
                        with redirect_stdout(devnull), redirect_stderr(devnull):  # type: ignore[name-defined]
                            self._withoutbg_model = WithoutBG.opensource()
                except Exception:
                    self._withoutbg_model = WithoutBG.opensource()
                logging.info("WithoutBG model initialized successfully")
            except Exception as exc:  # pragma: no cover - initialization failure path
                logging.error("Failed to initialize WithoutBG model: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize background removal model: {exc}",
                )

        if self._withoutbg_model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Background removal model failed to initialize. Please check server logs.",
            )
        return self._withoutbg_model

    def _upload_to_blob(self, file_stream: io.BytesIO, filename: str) -> str:
        """Upload a stream to blob storage under the dev container and return URL."""
        client = storage_service._get_blob_service_client()  # type: ignore[attr-defined]
        container = "dev"
        container_client = client.get_container_client(container)
        if not container_client.exists():
            container_client.create_container()

        blob_client = client.get_blob_client(container=container, blob=filename)
        blob_client.upload_blob(
            file_stream,
            overwrite=True,
            content_settings=ContentSettings(content_type="image/png"),
        )
        return blob_client.url

    async def process(
        self,
        db: AsyncSession,
        file: UploadFile,
        product_id: str,
    ) -> dict:
        """Remove background, upload to blob, save DB, and return response data."""
        allowed_types = {"image/png", "image/jpeg", "image/webp"}
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Allowed: image/png, image/jpeg, image/webp",
            )

        try:
            prod_uuid = uuid.UUID(product_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid productId format. Expected UUID string.",
            )

        product = await db.get(Product, prod_uuid)
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

        try:
            content = await file.read()
            if not content:
                raise ValueError("Empty file")
            input_image = Image.open(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to read image: {str(exc)}",
            )

        try:
            model = self._get_withoutbg_model()
            output_image = model.remove_background(input_image)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Background removal failed: {str(exc)}",
            )

        buffer = io.BytesIO()
        output_image.save(buffer, format="PNG")
        buffer.seek(0)
        file_size = buffer.getbuffer().nbytes

        file_token = uuid.uuid4().hex
        filename = f"{product_id}/{file_token}.png"
        try:
            blob_url = self._upload_to_blob(buffer, filename)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Blob upload failed: {str(exc)}",
            )

        try:
            asset_id_to_use = 11

            product_asset = ProductAsset(
                asset_id=asset_id_to_use,
                image=blob_url,
                size_bytes=file_size,
                created_by=None,
            )
            db.add(product_asset)
            await db.flush()

            product_asset_mapping = ProductAssetMapping(
                name=file.filename or "Processed Image",
                productid=prod_uuid,
                product_asset_id=product_asset.id,
                isactive=True,
                created_by=None,
            )
            db.add(product_asset_mapping)

            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database save failed: {str(exc)}",
            )

        return {
            "asset_id": asset_id_to_use,
            "blob_url": blob_url,
            "message": "Background removed and saved successfully",
            "image_size_bytes": file_size,
        }


background_removal_service = BackgroundRemovalService()

