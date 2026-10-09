"""Exam pause workflow: auto-pause after repeated looking-away, then a staff decision.

1. Each looking-away detection is recorded as an incident. When the count since the
   attempt started (or since staff last let the student continue) reaches the limit
   (PAUSE_AFTER_AWAY_COUNT, default 3), the attempt becomes "paused".
2. While paused the student cannot see questions or answer, and can ping staff.
3. Staff look at the captured images and either let the student continue (the count
   starts again from zero) or end the exam. Pausing is not a penalty; ending an exam
   is always a human decision.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AttemptStatus, ExamAttempt, IncidentType, ProctoringIncident, User

PAUSE_MESSAGE = "Your exam has been paused. Please contact the exam supervisor."
STATUS_MESSAGES = {
    AttemptStatus.paused: PAUSE_MESSAGE,
    AttemptStatus.submitted: "Exam already submitted",
    AttemptStatus.terminated: "Your exam was ended by the exam supervisor",
}


class InvalidTransition(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def away_count_since_resume(db: Session, attempt: ExamAttempt) -> int:
    since = attempt.last_resumed_at or attempt.started_at
    return (
        db.query(ProctoringIncident)
        .filter(
            ProctoringIncident.student_id == attempt.student_id,
            ProctoringIncident.examination_id == attempt.examination_id,
            ProctoringIncident.incident_type == IncidentType.looking_away,
            ProctoringIncident.timestamp >= since,
        )
        .count()
    )


def maybe_pause(db: Session, attempt: ExamAttempt, limit: int) -> bool:
    """Pause the attempt if the looking-away limit is reached. Returns True if it paused."""
    if limit <= 0 or attempt.status != AttemptStatus.in_progress:
        return False
    count = away_count_since_resume(db, attempt)
    if count < limit:
        return False
    attempt.status = AttemptStatus.paused
    attempt.paused_at = _now()
    attempt.pause_reason = f"Looking away detected {count} times"
    attempt.help_requested_at = None
    attempt.help_message = ""
    db.commit()
    return True


def request_help(db: Session, attempt: ExamAttempt, message: str) -> ExamAttempt:
    if attempt.status != AttemptStatus.paused:
        raise InvalidTransition("Help can only be requested while the exam is paused")
    attempt.help_requested_at = _now()
    attempt.help_message = message.strip()
    db.commit()
    return attempt


def _decide(db: Session, attempt: ExamAttempt, staff_user: User, note: str, status: AttemptStatus):
    if attempt.status != AttemptStatus.paused:
        raise InvalidTransition("Only a paused exam can be continued or ended")
    now = _now()
    attempt.status = status
    attempt.decision_note = note.strip()
    attempt.decided_by_id = staff_user.staff.id
    attempt.decided_at = now
    attempt.help_requested_at = None
    attempt.help_message = ""
    if status == AttemptStatus.in_progress:
        attempt.last_resumed_at = now  # restart the looking-away count
        attempt.paused_at = None
        attempt.pause_reason = ""
    else:
        attempt.submitted_at = now
    db.commit()
    return attempt


def resume(db: Session, attempt: ExamAttempt, staff_user: User, note: str = "") -> ExamAttempt:
    return _decide(db, attempt, staff_user, note, AttemptStatus.in_progress)


def terminate(db: Session, attempt: ExamAttempt, staff_user: User, note: str = "") -> ExamAttempt:
    return _decide(db, attempt, staff_user, note, AttemptStatus.terminated)
