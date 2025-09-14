import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

	APP_NAME: str = Field(default="Rivollo API")
	DEBUG: bool = Field(default=False)
	API_PREFIX: str = Field(default="")

	# Database
	DATABASE_URL: str = Field(default="")

	# Auth / JWT
	JWT_SECRET: str = Field(default="dev-change-me")
	JWT_ALGORITHM: str = Field(default="HS256")
	ACCESS_TOKEN_EXPIRES_MINUTES: int = Field(default=60)

	# Storage / CDN placeholders (wire Azure later)
	CDN_BASE_URL: str = Field(default="https://cdn.example")
	STORAGE_CONTAINER_UPLOADS: str = Field(default="uploads")
	AZURE_STORAGE_ACCOUNT: str = Field(default="")
	AZURE_STORAGE_KEY: str = Field(default="")
	AZURE_STORAGE_CONN_STRING: str = Field(default="")

	# External model service endpoint
	MODEL_SERVICE_URL: str = Field(default="mock://local")

	# Azure Monitor / Application Insights
	AZURE_MONITOR_CONN_STR: str = Field(default="")
	ENABLE_APP_INSIGHTS: bool = Field(default=True)
	SAMPLING_RATIO: float = Field(default=1.0)


settings = Settings()
