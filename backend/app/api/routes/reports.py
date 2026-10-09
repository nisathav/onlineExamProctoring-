"""Staff-only reporting and incident review (FR3 alerts, FR5). Human in the loop, no penalties."""
import logging
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_role
from app.db.session import get_db
from app.models import (
    ExamAttempt,
    Examination,
    ProctoringIncident,
    ReviewStatus,
    Student,
    StudentAnswer,
    User,
)
from app.schemas import (
    ExamReport,
    IncidentOut,
    AttemptDecision,
    IncidentReview,
    StudentSummary,
    StudentTimeline,
)
from app.services import deps
from app.services import pause
from app.services.analysis import flag_reasons

log = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])
staff_only = require_role("staff")


def _reasons(incidents) -> list[str]:
    s = get_settings()
    return flag_reasons(
        incidents,
        away_count=s.flag_away_count,
        window_seconds=s.flag_window_seconds,
        long_away_seconds=s.long_away_seconds,
        capture_interval_seconds=s.capture_interval_seconds,
    )


def _incident_out(incident: ProctoringIncident, storage) -> IncidentOut:
    out = IncidentOut.model_validate(incident)
    if incident.evidence_key and storage is not None:
        try:
            out.evidence_url = storage.presigned_url(incident.evidence_key)
        except Exception:
            log.exception("Could not presign %s", incident.evidence_key)
    return out


@router.get("/exams/{exam_id}", response_model=ExamReport)
def exam_report(exam_id: int, _: User = Depends(staff_only), db: Session = Depends(get_db)):
    exam = db.get(Examination, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Examination not found")
    max_score = float(sum(q.marks for q in exam.questions))

    attempts = {a.student_id: a for a in db.query(ExamAttempt).filter_by(examination_id=exam_id)}
    incidents_by_student: dict[int, list[ProctoringIncident]] = {}
    for inc in (
        db.query(ProctoringIncident)
        .filter_by(examination_id=exam_id)
        .order_by(ProctoringIncident.timestamp)
    ):
        incidents_by_student.setdefault(inc.student_id, []).append(inc)
    scores = dict(
        db.query(StudentAnswer.student_id, func.sum(StudentAnswer.marks_obtained))
        .filter_by(examination_id=exam_id)
        .group_by(StudentAnswer.student_id)
        .all()
    )

    student_ids = set(attempts) | set(incidents_by_student)
    students = db.query(Student).filter(Student.id.in_(student_ids)).all() if student_ids else []
    summaries = []
    for student in sorted(students, key=lambda s: s.user.username):
        incs = incidents_by_student.get(student.id, [])
        reasons = _reasons(incs)
        attempt = attempts.get(student.id)
        summaries.append(
            StudentSummary(
                student_id=student.id,
                username=student.user.username,
                full_name=student.user.full_name,
                attempt_status=attempt.status.value if attempt else None,
                incident_count=len(incs),
                incidents_by_type=dict(Counter(i.incident_type.value for i in incs)),
                first_incident=incs[0].timestamp if incs else None,
                last_incident=incs[-1].timestamp if incs else None,
                score=float(scores.get(student.id) or 0.0),
                max_score=max_score,
                flagged=bool(reasons),
                flag_reasons=reasons,
                pending_reviews=sum(1 for i in incs if i.review_status == ReviewStatus.pending),
                paused_at=attempt.paused_at if attempt else None,
                pause_reason=(attempt.pause_reason or "") if attempt else "",
                help_requested_at=attempt.help_requested_at if attempt else None,
                help_message=(attempt.help_message or "") if attempt else "",
            )
        )
    return ExamReport(examination_id=exam.id, title=exam.title, students=summaries)


@router.get("/exams/{exam_id}/students/{student_id}", response_model=StudentTimeline)
def student_timeline(
    exam_id: int,
    student_id: int,
    _: User = Depends(staff_only),
    db: Session = Depends(get_db),
    storage=Depends(deps.get_storage),
):
    student = db.get(Student, student_id)
    if student is None or db.get(Examination, exam_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    incidents = (
        db.query(ProctoringIncident)
        .filter_by(examination_id=exam_id, student_id=student_id)
        .order_by(ProctoringIncident.timestamp)
        .all()
    )
    reasons = _reasons(incidents)
    attempt = db.query(ExamAttempt).filter_by(examination_id=exam_id, student_id=student_id).first()
    return StudentTimeline(
        examination_id=exam_id,
        student_id=student_id,
        username=student.user.username,
        attempt_status=attempt.status.value if attempt else None,
        paused_at=attempt.paused_at if attempt else None,
        pause_reason=(attempt.pause_reason or "") if attempt else "",
        help_requested_at=attempt.help_requested_at if attempt else None,
        help_message=(attempt.help_message or "") if attempt else "",
        decision_note=(attempt.decision_note or "") if attempt else "",
        decided_at=attempt.decided_at if attempt else None,
        flagged=bool(reasons),
        flag_reasons=reasons,
        incidents=[_incident_out(i, storage) for i in incidents],
    )


@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
def review_incident(
    incident_id: int,
    body: IncidentReview,
    user: User = Depends(staff_only),
    db: Session = Depends(get_db),
):
    incident = db.get(ProctoringIncident, incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    incident.review_status = ReviewStatus(body.review_status)
    incident.reviewer_note = body.note
    incident.reviewed_by_id = user.staff.id
    incident.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)
    return _incident_out(incident, None)


def _paused_attempt(db: Session, exam_id: int, student_id: int) -> ExamAttempt:
    attempt = db.query(ExamAttempt).filter_by(examination_id=exam_id, student_id=student_id).first()
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    return attempt


def _decision_response(attempt: ExamAttempt) -> dict:
    return {"student_id": attempt.student_id, "examination_id": attempt.examination_id,
            "attempt_status": attempt.status.value, "decision_note": attempt.decision_note}


@router.post("/exams/{exam_id}/students/{student_id}/resume")
def resume_attempt(
    exam_id: int,
    student_id: int,
    body: AttemptDecision,
    user: User = Depends(staff_only),
    db: Session = Depends(get_db),
):
    """Staff decision: the paused student may continue. The looking-away count restarts."""
    attempt = _paused_attempt(db, exam_id, student_id)
    try:
        pause.resume(db, attempt, user, body.note)
    except pause.InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _decision_response(attempt)


@router.post("/exams/{exam_id}/students/{student_id}/terminate")
def terminate_attempt(
    exam_id: int,
    student_id: int,
    body: AttemptDecision,
    user: User = Depends(staff_only),
    db: Session = Depends(get_db),
):
    """Staff decision: the paused student may not continue; the exam ends with answers so far."""
    attempt = _paused_attempt(db, exam_id, student_id)
    try:
        pause.terminate(db, attempt, user, body.note)
    except pause.InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _decision_response(attempt)
