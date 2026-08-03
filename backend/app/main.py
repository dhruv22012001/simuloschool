import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import seed_admin
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.request_id import RequestIdMiddleware
from app.routers import admin, auth, health, videos

configure_logging()


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Say out loud what this process is configured to talk to. Without it, a
    # misconfigured deploy looks identical to a broken one in the logs.
    logger.info(
        "starting api",
        extra={
            "ctx": {
                "env": settings.app_env,
                "db_host": settings.database_host,
                "cors_origins": settings.cors_origins_list,
                "storage_endpoint": settings.s3_endpoint_url or "(unset)",
            }
        },
    )
    for problem in settings.validate_for_production():
        logger.error("configuration problem", extra={"ctx": {"problem": problem}})

    seed_admin()
    yield


app = FastAPI(title="SimuloSchool API", lifespan=lifespan)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(admin.router)
