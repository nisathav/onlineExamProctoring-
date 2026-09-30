"""Hardening and data handling: API-1..API-5, DATA-1..DATA-3."""
import base64
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.middleware import HTTPSRedirectMiddleware, SecurityHeadersMiddleware
from app.models import IncidentType, ProctoringIncident, Student
from app.services.retention import purge_evidence


def test_api_1_health_and_docs(client):
    """API-1: /health is public; OpenAPI docs list the secured routes."""
    assert client.get("/health").json()["status"] == "ok"
    spec = client.get("/openapi.json").json()
    assert "/proctoring/frame" in spec["paths"]
    assert "OAuth2PasswordBearer" in spec["components"]["securitySchemes"]


def test_api_2_security_headers(client):
    """API-2: security headers on every response."""
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_api_3_cors_only_frontend_origin(client):
    """API-3: CORS allows only the configured front-end origin."""
    allowed = get_settings().frontend_origin
    ok = client.options("/exams", headers={"Origin": allowed, "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == allowed
    bad = client.options("/exams", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_api_4_frame_size_limit(client, student_headers, started_exam):
    """API-4: oversized frames are rejected with 413 before processing."""
    huge = base64.b64encode(b"\xff" * (get_settings().max_frame_bytes + 10)).decode()
    r = client.post("/proctoring/frame", headers=student_headers, json={"exam_id": started_exam, "image": huge})
    assert r.status_code == 413


def test_api_4b_decoded_frame_size_limit(client, student_headers, started_exam, monkeypatch):
    """API-4: the decoded-size check also applies (e.g. multipart)."""
    monkeypatch.setattr(get_settings(), "max_frame_bytes", 10)
    r = client.post("/proctoring/frame", headers=student_headers, data={"exam_id": str(started_exam)},
                    files={"file": ("f.jpg", b"x" * 11, "image/jpeg")})
    assert r.status_code == 413


def test_api_5_https_redirect_and_hsts():
    """API-5: production redirects HTTP to HTTPS and sets HSTS."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts=True)
    app.add_middleware(HTTPSRedirectMiddleware)

    @app.get("/x")
    def x():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    c = TestClient(app)
    r = c.get("/x", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith("https://")
    assert c.get("/health").status_code == 200
    r = c.get("/x", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200 and "max-age" in r.headers["strict-transport-security"]


def test_api_5b_no_tokens_in_urls(client):
    """API-5: auth uses the Authorization header, not query strings."""
    r = client.get("/auth/me?access_token=abc")
    assert r.status_code == 401


def test_data_1_consent_recorded(client, student_headers):
    """DATA-1: consent screen info and timestamp are recorded once."""
    before = client.get("/auth/consent", headers=student_headers).json()
    assert before["consent_given_at"] is None
    assert before["capture_interval_seconds"] == 3 and before["retention_days"] == get_settings().evidence_retention_days
    first = client.post("/auth/consent", headers=student_headers).json()["consent_given_at"]
    again = client.post("/auth/consent", headers=student_headers).json()["consent_given_at"]
    assert first and first.rstrip("Z") == again.rstrip("Z")  # SQLite drops tz


def test_data_2_students_cannot_see_incidents_or_evidence(client, student_headers, started_exam, db):
    """DATA-2: evidence is only reachable through staff-only presigned URLs."""
    student = db.query(Student).first()
    assert client.get(f"/reports/exams/{started_exam}/students/{student.id}", headers=student_headers).status_code == 403


def test_data_3_retention_purges_old_evidence(db, started_exam):
    """DATA-3: evidence older than the retention period is deleted; incidents are kept."""
    from tests.conftest import FakeStorage

    storage = FakeStorage()
    student = db.query(Student).first()
    now = datetime.now(timezone.utc)
    for days, key in [(40, "old.jpg"), (1, "new.jpg")]:
        storage.objects[key] = b"x"
        db.add(ProctoringIncident(student_id=student.id, examination_id=started_exam,
                                  timestamp=now - timedelta(days=days),
                                  incident_type=IncidentType.no_face, evidence_key=key))
    db.commit()
    assert purge_evidence(db, storage, retention_days=30, now=now) == 1
    assert set(storage.objects) == {"new.jpg"}
    keys = sorted(str(i.evidence_key) for i in db.query(ProctoringIncident))
    assert keys == ["None", "new.jpg"]
