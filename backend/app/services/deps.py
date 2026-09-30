"""Process-wide singletons (ML models, storage, thread pool) exposed as FastAPI dependencies.

Tests override these with fakes via app.dependency_overrides.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from app.core.config import get_settings
from app.services.face_detector import FaceDetector
from app.services.gaze_service import GazeService

log = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_detector: FaceDetector | None = None
_gaze: GazeService | None = None
_storage = None


def executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=get_settings().ml_workers, thread_name_prefix="ml")
    return _executor


async def run_ml(fn, *args, **kwargs):
    """Run heavy ML work off the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor(), partial(fn, *args, **kwargs))


def get_face_detector() -> FaceDetector:
    global _detector
    if _detector is None:
        _detector = FaceDetector()
    return _detector


def get_gaze_service() -> GazeService:
    global _gaze
    if _gaze is None:
        s = get_settings()
        _gaze = GazeService(s.gaze_model_path, s.gaze_threshold)
    return _gaze


def get_storage():
    global _storage
    if _storage is None:
        from app.services.storage import EvidenceStorage

        _storage = EvidenceStorage(get_settings())
    return _storage


def startup() -> None:
    """Load the model and prepare the bucket; failures are logged, not fatal."""
    try:
        get_gaze_service().load()
    except Exception:  # pragma: no cover - depends on TF install / model file
        log.exception("Failed to load gaze model")
    try:  # warm up MediaPipe in each ML worker so the first frames are fast
        import numpy as np

        blank = np.zeros((240, 320, 3), np.uint8)
        workers = get_settings().ml_workers
        list(executor().map(lambda _: get_face_detector().analyze(blank), range(workers * 2)))
    except Exception:  # pragma: no cover - depends on MediaPipe install
        log.exception("MediaPipe warm-up failed")
    try:
        get_storage().ensure_bucket()
    except Exception:  # pragma: no cover - depends on MinIO being up
        log.exception("MinIO not reachable at startup")


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False)
        _executor = None
