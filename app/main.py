from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.uploads import router as uploads_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.assets import router as assets_router
from app.api.routes.blueprints import router as blueprints_router
from app.utils.envelopes import api_success, api_error
from app.core.db import init_engine_and_session


app = FastAPI(title=settings.APP_NAME)

# CORS (adjust for real origins later)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Normalize API prefix (must not end with '/')
_api_prefix = settings.API_PREFIX.rstrip("/")

# Include routers
app.include_router(auth_router, prefix=_api_prefix)
app.include_router(users_router, prefix=_api_prefix)
app.include_router(uploads_router, prefix=_api_prefix)
app.include_router(jobs_router, prefix=_api_prefix)
app.include_router(assets_router, prefix=_api_prefix)
app.include_router(blueprints_router, prefix=_api_prefix)


@app.on_event("startup")
def on_startup() -> None:
	init_engine_and_session()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
	return JSONResponse(status_code=500, content=api_error(code="INTERNAL_SERVER_ERROR", message="An unexpected error occurred"))


@app.get("/")
async def root():
	return api_success({"service": settings.APP_NAME, "status": "ok"})
