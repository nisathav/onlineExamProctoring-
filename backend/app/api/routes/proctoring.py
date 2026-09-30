"""POST /proctoring/frame: one webcam frame every 3 s from the student's browser (FR3)."""
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_role
from app.db.session import get_db
from app.models import AttemptStatus, ExamAttempt, Examination, ProctoringIncident, User
from app.schemas import FrameIn, FrameResult
from app.services import deps
from app.services.proctoring import InvalidImage, analyze_frame, decode_base64_image
from app.services.storage import evidence_key

log = logging.getLogger(__name__)
router = APIRouter(prefix="/proctoring", tags=["proctoring"])


async def _read_frame(request: Request) -> tuple[int, bytes]:
    """Accept JSON {exam_id, image: base64} or multipart (exam_id, file)."""
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file is required")
            return int(form.get("exam_id", "")), await upload.read()
        body = FrameIn.model_validate(await request.json())
        return body.exam_id, decode_base64_image(body.image)
    except InvalidImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # malformed JSON, missing/invalid exam_id, validation errors
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid frame payload") from exc


@router.post(
    "/frame",
    response_model=FrameResult,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {"schema": FrameIn.model_json_schema()},
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "exam_id": {"type": "integer"},
                            "file": {"type": "string", "format": "binary"},
                        },
                        "required": ["exam_id", "file"],
                    }
                },
            },
            "required": True,
        }
    },
)
async def post_frame(
    request: Request,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
    detector=Depends(deps.get_face_detector),
    gaze=Depends(deps.get_gaze_service),
    storage=Depends(deps.get_storage),
):
    started = time.perf_counter()
    exam_id, raw = await _read_frame(request)
    if len(raw) > get_settings().max_frame_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Frame too large")

    exam = db.get(Examination, exam_id)
    attempt = (
        db.query(ExamAttempt).filter_by(student_id=user.student.id, examination_id=exam_id).first()
    )
    if exam is None or attempt is None or attempt.status != AttemptStatus.in_progress:
        raise HTTPException(status.HTTP_409_CONFLICT, "No exam in progress for this exam_id")

    try:
        decision = await deps.run_ml(analyze_frame, raw, detector, gaze)
    except InvalidImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    incident_id = None
    if decision.incident_type is not None:
        now = datetime.now(timezone.utc)
        key = evidence_key(user.username, exam_id, now)
        try:
            await deps.run_ml(storage.put_jpeg, key, raw)
        except Exception:
            log.exception("Failed to store evidence %s", key)
            key = None
        incident = ProctoringIncident(
            student_id=user.student.id,
            examination_id=exam_id,
            timestamp=now,
            incident_type=decision.incident_type,
            confidence=decision.confidence,
            evidence_key=key,
        )
        db.add(incident)
        db.commit()
        incident_id = incident.id

    elapsed_ms = (time.perf_counter() - started) * 1000
    log.info(
        "frame user=%s exam=%s faces=%s gaze=%s incident=%s %.1fms",
        user.username, exam_id, decision.face_count, decision.gaze,
        decision.incident_type.value if decision.incident_type else None, elapsed_ms,
    )
    return FrameResult(
        face_detected=decision.face_detected,
        face_count=decision.face_count,
        gaze=decision.gaze,
        confidence=decision.confidence,
        warning=decision.warning,
        incident_id=incident_id,
        processing_ms=round(elapsed_ms, 1),
    )
