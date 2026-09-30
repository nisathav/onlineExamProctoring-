"""Staff reports, temporal flags and incident review (FR3 alerts, FR5)."""
from datetime import datetime, timedelta, timezone

from app.models import IncidentType, ProctoringIncident, Student
from app.services.analysis import flag_reasons

T0 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _inc(seconds, kind=IncidentType.looking_away):
    return ProctoringIncident(timestamp=T0 + timedelta(seconds=seconds), incident_type=kind)


def test_flag_burst_of_away_incidents():
    """3+ face-away incidents within 30 s -> flagged."""
    assert flag_reasons([_inc(0), _inc(40), _inc(80)]) == []
    reasons = flag_reasons([_inc(0), _inc(12), _inc(29)])
    assert any("within 30s" in r for r in reasons)


def test_flag_long_away_period():
    """Consecutive away/no-face captures spanning 15 s -> flagged."""
    run = [_inc(s, IncidentType.no_face) for s in range(0, 16, 3)]  # 0..15, no_face only
    assert flag_reasons(run) == ["Away from screen for 15s or longer"]
    gappy = [_inc(0, IncidentType.no_face), _inc(10, IncidentType.no_face), _inc(20, IncidentType.no_face)]
    assert flag_reasons(gappy) == []


def test_flag_multiple_faces():
    assert flag_reasons([_inc(0, IncidentType.multiple_faces)]) == ["Multiple faces detected"]


def _add_incidents(db, exam_id, seconds, key=True):
    student = db.query(Student).first()
    now = datetime.now(timezone.utc)
    for s in seconds:
        db.add(ProctoringIncident(student_id=student.id, examination_id=exam_id,
                                  timestamp=now + timedelta(seconds=s),
                                  incident_type=IncidentType.looking_away, confidence=0.9,
                                  evidence_key=f"student1/{exam_id}/{s}.jpg" if key else None))
    db.commit()
    return student.id


def test_exam_report_summarises_students(client, staff_headers, student_headers, started_exam, db):
    """Per-student counts, first/last incident, score and flags."""
    sid = _add_incidents(db, started_exam, [0, 5, 10])
    report = client.get(f"/reports/exams/{started_exam}", headers=staff_headers).json()
    assert report["title"] == "Sample Computing Quiz"
    row = report["students"][0]
    assert row["student_id"] == sid and row["username"] == "student1"
    assert row["incident_count"] == 3 and row["incidents_by_type"] == {"looking_away": 3}
    assert row["flagged"] and row["pending_reviews"] == 3
    assert row["attempt_status"] == "in_progress" and row["max_score"] == 10
    assert row["first_incident"] < row["last_incident"]


def test_student_timeline_has_presigned_urls_and_review(client, staff_headers, started_exam, db):
    """Timeline returns presigned evidence URLs; staff mark incidents reviewed (no auto penalty)."""
    sid = _add_incidents(db, started_exam, [0, 40], key=True)
    timeline = client.get(f"/reports/exams/{started_exam}/students/{sid}", headers=staff_headers).json()
    assert timeline["flagged"] is False and len(timeline["incidents"]) == 2
    first = timeline["incidents"][0]
    assert "X-Amz-Signature" in first["evidence_url"] and first["review_status"] == "pending"

    r = client.patch(f"/reports/incidents/{first['id']}", headers=staff_headers,
                     json={"review_status": "needs_follow_up", "note": "check with student"})
    assert r.status_code == 200 and r.json()["review_status"] == "needs_follow_up"
    assert client.patch(f"/reports/incidents/{first['id']}", headers=staff_headers,
                        json={"review_status": "penalise"}).status_code == 422
    assert client.patch("/reports/incidents/9999", headers=staff_headers,
                        json={"review_status": "reviewed_ok"}).status_code == 404

    report = client.get(f"/reports/exams/{started_exam}", headers=staff_headers).json()
    assert report["students"][0]["pending_reviews"] == 1


def test_reports_not_found(client, staff_headers, exam_id):
    assert client.get("/reports/exams/9999", headers=staff_headers).status_code == 404
    assert client.get(f"/reports/exams/{exam_id}/students/9999", headers=staff_headers).status_code == 404


def test_empty_report(client, staff_headers, exam_id):
    assert client.get(f"/reports/exams/{exam_id}", headers=staff_headers).json()["students"] == []
