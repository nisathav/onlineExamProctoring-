"""Auto-pause after repeated looking-away and the staff decision: EXAM-5..EXAM-9, INT-7."""
import base64

import pytest

from app.models import AttemptStatus, ExamAttempt, IncidentType, ProctoringIncident
from app.services.face_detector import FaceAnalysis


def frame(client, headers, exam_id, raw):
    return client.post("/proctoring/frame", headers=headers,
                       json={"exam_id": exam_id, "image": base64.b64encode(raw).decode()})


def look_away(client, headers, exam_id, raw, fakes, times):
    fakes[1].prob_at = 0.05
    return [frame(client, headers, exam_id, raw) for _ in range(times)]


def attempt(db, exam_id):
    db.expire_all()
    return db.query(ExamAttempt).filter_by(examination_id=exam_id).one()


def test_exam_5_pauses_after_three_looking_away(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """EXAM-5: the 3rd looking-away detection pauses the exam and tells the student."""
    r1, r2, r3 = look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 3)
    assert not r1.json()["exam_paused"] and not r2.json()["exam_paused"]
    body = r3.json()
    assert body["exam_paused"] is True and "contact the exam supervisor" in body["pause_message"]
    a = attempt(db, started_exam)
    assert a.status == AttemptStatus.paused and a.paused_at and "3 times" in a.pause_reason


def test_exam_5b_other_incidents_do_not_count(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """EXAM-5: missing-face and looking-at frames do not count towards the pause."""
    detector, gaze, _ = fakes
    detector.next = FaceAnalysis(face_count=0)
    for _ in range(4):
        assert frame(client, student_headers, started_exam, jpeg_bytes).json()["exam_paused"] is False
    assert attempt(db, started_exam).status == AttemptStatus.in_progress


def test_exam_5c_limit_is_configurable(client, student_headers, started_exam, fakes, jpeg_bytes, db, monkeypatch):
    """EXAM-5: PAUSE_AFTER_AWAY_COUNT=0 disables auto-pause."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "pause_after_away_count", 0)
    look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 4)
    assert attempt(db, started_exam).status == AttemptStatus.in_progress


def test_exam_6_paused_exam_blocks_questions_answers_frames(client, student_headers, started_exam, fakes, jpeg_bytes):
    """EXAM-6: while paused the student cannot read questions, answer, submit or send frames."""
    look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 3)
    for r in (
        client.get(f"/exams/{started_exam}/questions/0", headers=student_headers),
        client.post(f"/exams/{started_exam}/answers", json={"question_id": 1, "answer": "x"}, headers=student_headers),
        client.post(f"/exams/{started_exam}/submit", headers=student_headers),
        frame(client, student_headers, started_exam, jpeg_bytes),
    ):
        assert r.status_code == 409 and "contact the exam supervisor" in r.json()["detail"]
    # Reloading the page (start again) returns the paused attempt instead of an error.
    r = client.post(f"/exams/{started_exam}/start", headers=student_headers)
    assert r.status_code == 200 and r.json()["status"] == "paused"


def test_exam_7_student_pings_staff(client, student_headers, staff_headers, started_exam, fakes, jpeg_bytes):
    """EXAM-7: the paused student can notify the supervisor; staff see it on the dashboard."""
    assert client.post(f"/exams/{started_exam}/help", json={"message": "x"},
                       headers=student_headers).status_code == 409  # not paused yet
    look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 3)
    r = client.post(f"/exams/{started_exam}/help", json={"message": "I dropped my pen"}, headers=student_headers)
    assert r.status_code == 200 and r.json()["help_requested_at"]
    assert client.get(f"/exams/{started_exam}/attempt", headers=student_headers).json()["status"] == "paused"

    row = client.get(f"/reports/exams/{started_exam}", headers=staff_headers).json()["students"][0]
    assert row["attempt_status"] == "paused" and row["paused_at"]
    assert row["help_requested_at"] and row["help_message"] == "I dropped my pen"
    timeline = client.get(f"/reports/exams/{started_exam}/students/{row['student_id']}", headers=staff_headers).json()
    assert timeline["attempt_status"] == "paused" and timeline["help_message"] == "I dropped my pen"
    assert sum(i["incident_type"] == "looking_away" for i in timeline["incidents"]) == 3


def test_exam_8_staff_lets_student_continue(client, student_headers, staff_headers, started_exam, fakes, jpeg_bytes, db):
    """EXAM-8: 'allow to continue' unpauses, and the count restarts from zero."""
    look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 3)
    sid = attempt(db, started_exam).student_id
    r = client.post(f"/reports/exams/{started_exam}/students/{sid}/resume",
                    json={"note": "checked images, notes on desk"}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["attempt_status"] == "in_progress"
    a = attempt(db, started_exam)
    assert a.last_resumed_at and a.decided_by_id and a.decision_note == "checked images, notes on desk"
    assert a.help_requested_at is None

    assert client.get(f"/exams/{started_exam}/questions/0", headers=student_headers).status_code == 200
    r1, r2 = look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 2)
    assert not r2.json()["exam_paused"]  # earlier incidents no longer count
    assert look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 1)[0].json()["exam_paused"]
    # Resuming an exam that is not paused is rejected.
    client.post(f"/reports/exams/{started_exam}/students/{sid}/resume", json={}, headers=staff_headers)
    assert client.post(f"/reports/exams/{started_exam}/students/{sid}/resume", json={},
                       headers=staff_headers).status_code == 409


def test_exam_9_staff_ends_exam(client, student_headers, staff_headers, started_exam, fakes, jpeg_bytes, db):
    """EXAM-9: 'end exam' terminates the attempt; the student sees the result, cannot continue."""
    look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 3)
    sid = attempt(db, started_exam).student_id
    r = client.post(f"/reports/exams/{started_exam}/students/{sid}/terminate",
                    json={"note": "phone visible"}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["attempt_status"] == "terminated"
    me = client.get(f"/exams/{started_exam}/attempt", headers=student_headers).json()
    assert me["status"] == "terminated" and me["decision_note"] == "phone visible"
    progress = client.get(f"/exams/{started_exam}/progress", headers=student_headers).json()
    assert progress["status"] == "terminated" and progress["score"] == 0
    r = client.get(f"/exams/{started_exam}/questions/0", headers=student_headers)
    assert r.status_code == 409 and "ended by the exam supervisor" in r.json()["detail"]
    assert client.post(f"/exams/{started_exam}/start", headers=student_headers).status_code == 409
    assert client.post(f"/reports/exams/{started_exam}/students/{sid}/terminate", json={},
                       headers=staff_headers).status_code == 409


def test_int_7_decisions_are_staff_only(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """INT-7: students cannot resume or end attempts; unknown attempts give 404."""
    look_away(client, student_headers, started_exam, jpeg_bytes, fakes, 3)
    sid = attempt(db, started_exam).student_id
    for action in ("resume", "terminate"):
        r = client.post(f"/reports/exams/{started_exam}/students/{sid}/{action}", json={}, headers=student_headers)
        assert r.status_code == 403


def test_attempt_endpoints_not_found(client, student_headers, staff_headers, exam_id):
    assert client.get(f"/exams/{exam_id}/attempt", headers=student_headers).status_code == 404
    assert client.post(f"/exams/{exam_id}/help", json={}, headers=student_headers).status_code == 404
    assert client.post(f"/reports/exams/{exam_id}/students/999/resume", json={},
                       headers=staff_headers).status_code == 404


def test_help_message_length_limited(client, student_headers, started_exam):
    r = client.post(f"/exams/{started_exam}/help", json={"message": "x" * 501}, headers=student_headers)
    assert r.status_code == 422


@pytest.mark.parametrize("count,paused", [(2, False), (3, True)])
def test_away_count_since_resume(db, started_exam, count, paused):
    from datetime import datetime, timedelta, timezone

    from app.services import pause

    a = attempt(db, started_exam)
    for i in range(count):
        db.add(ProctoringIncident(student_id=a.student_id, examination_id=started_exam,
                                  timestamp=datetime.now(timezone.utc) + timedelta(seconds=i),
                                  incident_type=IncidentType.looking_away))
    db.commit()
    assert pause.away_count_since_resume(db, a) == count
    assert pause.maybe_pause(db, a, 3) is paused
