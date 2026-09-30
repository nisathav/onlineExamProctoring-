import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, exams, proctoring, reports
from app.core.config import get_settings
from app.core.middleware import (
    BodySizeLimitMiddleware,
    HTTPSRedirectMiddleware,
    SecurityHeadersMiddleware,
)
from app.services import deps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    retention_task = None
    if settings.environment != "test":
        await asyncio.get_running_loop().run_in_executor(None, deps.startup)
        from app.services.retention import retention_loop

        retention_task = asyncio.create_task(retention_loop())
    yield
    if retention_task:
        retention_task.cancel()
    deps.shutdown()


app = FastAPI(
    title="Enhanced Online Proctoring System",
    version="1.0.0",
    description="Webcam gaze monitoring for online exams. Flags are decision support only.",
    lifespan=lifespan,
)

production = settings.environment == "production"
# Base64 inflates a JPEG by ~4/3, plus JSON overhead.
app.add_middleware(
    BodySizeLimitMiddleware, limits={"/proctoring/frame": settings.max_frame_bytes * 4 // 3 + 4096}
)
app.add_middleware(SecurityHeadersMiddleware, hsts=production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
if production:
    app.add_middleware(HTTPSRedirectMiddleware)

app.include_router(auth.router)
app.include_router(exams.router)
app.include_router(proctoring.router)
app.include_router(reports.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "model_loaded": deps.get_gaze_service().loaded}
