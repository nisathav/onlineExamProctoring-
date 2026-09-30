"""Face/gaze pipeline and /proctoring/frame: FACE-1..FACE-8, INT-2, INT-4."""
import base64
import threading

import numpy as np
import pytest

from app.models import ProctoringIncident
from app.services import deps
from app.services.face_detector import (
    FaceAnalysis,
    Orientation,
    crop_with_margin,
    orientation_from_landmarks,
)
from app.services.gaze_service import adjusted_threshold, classify, preprocess_face
from app.services.proctoring import InvalidImage, decode_base64_image
from app.services.storage import evidence_key


def post_frame(client, headers, exam_id, raw):
    return client.post("/proctoring/frame", headers=headers,
                       json={"exam_id": exam_id, "image": base64.b64encode(raw).decode()})


# ---------- pure logic ----------
def test_face_1_threshold_unchanged_for_frontal_face():
    """FACE-1: frontal face keeps the 0.5 base threshold."""
    assert adjusted_threshold(0.5, Orientation()) == 0.5
    assert adjusted_threshold(0.5, None) == 0.5
    assert classify(0.51, 0.5, Orientation()).gaze == "at"
    assert classify(0.49, 0.5, Orientation()).gaze == "away"


@pytest.mark.parametrize("tilt,expected", [(5, 0.5), (10, 0.5), (15, 0.4125), (20, 0.375), (30, 0.3), (60, 0.3)])
def test_face_2_tilt_lowers_threshold(tilt, expected):
    """FACE-2: head tilt >10 deg relaxes the threshold (orientation-based adaptive threshold)."""
    assert adjusted_threshold(0.5, Orientation(tilt_degrees=tilt)) == pytest.approx(expected)
    assert adjusted_threshold(0.5, Orientation(tilt_degrees=-tilt)) == pytest.approx(expected)


def test_face_3_turned_and_smiling_adjustments_have_floors():
    """FACE-3: eye asymmetry and smiling lower the threshold, never below the floors."""
    assert adjusted_threshold(0.5, Orientation(eye_width_ratio=0.7)) == pytest.approx(0.45)
    assert adjusted_threshold(0.5, Orientation(smile_ratio=5)) == pytest.approx(0.42)
    worst = Orientation(tilt_degrees=45, eye_width_ratio=0.5, smile_ratio=9)
    assert adjusted_threshold(0.5, worst) == pytest.approx(0.17)
    assert adjusted_threshold(0.2, worst) == pytest.approx(0.15)


def test_face_3b_confidence_is_for_predicted_class():
    pred = classify(0.2, 0.5, None)
    assert pred.gaze == "away" and pred.confidence == pytest.approx(0.8)


def test_face_4_orientation_from_landmarks():
    """FACE-4: orientation geometry from face-mesh landmarks."""
    level = {33: (100, 100), 133: (130, 100), 263: (200, 100), 362: (170, 100),
             61: (120, 200), 291: (180, 200), 0: (150, 190), 17: (150, 210)}
    o = orientation_from_landmarks(level)
    assert o.tilt_degrees == pytest.approx(0) and o.eye_width_ratio == pytest.approx(1)
    assert o.smile_ratio == pytest.approx(3) and not o.is_smiling

    tilted = {**level, 263: (200, 200)}
    assert orientation_from_landmarks(tilted).tilt_degrees == pytest.approx(45)
    turned = {**level, 362: (185, 100)}
    assert orientation_from_landmarks(turned).eye_width_ratio == pytest.approx(0.5)


def test_face_5_preprocess_matches_training_pipeline():
    """FACE-5: face crop -> 224x224x3 float RGB in raw 0-255 range (model rescales itself)."""
    face = np.random.default_rng(0).integers(0, 255, (97, 83, 3), dtype=np.uint8)
    out = preprocess_face(face)
    assert out.shape == (224, 224, 3) and out.dtype == np.float32
    assert out.max() > 1.0 and out.min() >= 0


def test_face_5b_crop_with_margin_is_clamped():
    img = np.zeros((100, 100, 3), np.uint8)
    assert crop_with_margin(img, (40, 40, 20, 20)).shape == (28, 28, 3)
    assert crop_with_margin(img, (0, 0, 100, 100)).shape == (100, 100, 3)


def test_evidence_key_format():
    from datetime import datetime, timezone

    key = evidence_key("student1", 7, datetime(2025, 3, 7, 16, 36, 1, 5000, tzinfo=timezone.utc))
    assert key == "student1/7/20250307T163601005000Z.jpg"


def test_decode_base64_image():
    assert decode_base64_image("data:image/jpeg;base64," + base64.b64encode(b"abc").decode()) == b"abc"
    with pytest.raises(InvalidImage):
        decode_base64_image("!!!not base64!!!")


# ---------- endpoint ----------
def test_face_6_looking_at_screen_no_incident(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """FACE-6: single face looking at screen -> no warning, no incident, no evidence."""
    _, gaze, storage = fakes
    gaze.prob_at = 0.93
    r = post_frame(client, student_headers, started_exam, jpeg_bytes)
    assert r.status_code == 200
    body = r.json()
    assert body["face_detected"] and body["face_count"] == 1 and body["gaze"] == "at"
    assert body["warning"] is None and body["incident_id"] is None
    assert body["confidence"] == pytest.approx(0.93)
    assert db.query(ProctoringIncident).count() == 0 and storage.objects == {}


def test_face_7_looking_away_records_incident(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """FACE-7: gaze away -> warning, incident row and evidence saved as {username}/{exam}/{ts}.jpg."""
    _, gaze, storage = fakes
    gaze.prob_at = 0.1
    body = post_frame(client, student_headers, started_exam, jpeg_bytes).json()
    assert body["gaze"] == "away" and "looking away" in body["warning"]
    incident = db.get(ProctoringIncident, body["incident_id"])
    assert incident.incident_type.value == "looking_away"
    assert incident.confidence == pytest.approx(0.9)
    assert incident.evidence_key.startswith(f"student1/{started_exam}/")
    assert storage.objects[incident.evidence_key] == jpeg_bytes


def test_face_7b_tilted_face_borderline_counts_as_at(client, student_headers, started_exam, fakes, jpeg_bytes):
    """FACE-7: prob 0.4 is 'away' frontal but 'at' with a 20 deg tilt (adaptive threshold)."""
    detector, gaze, _ = fakes
    gaze.prob_at = 0.4
    assert post_frame(client, student_headers, started_exam, jpeg_bytes).json()["gaze"] == "away"
    detector.next.orientation = Orientation(tilt_degrees=20)
    assert post_frame(client, student_headers, started_exam, jpeg_bytes).json()["gaze"] == "at"


def test_face_8_no_face_and_multiple_faces(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """FACE-8: missing face or extra faces are incidents even without gaze classification."""
    detector, _, _ = fakes
    detector.next = FaceAnalysis(face_count=0)
    body = post_frame(client, student_headers, started_exam, jpeg_bytes).json()
    assert body["face_detected"] is False and body["gaze"] is None and "No face" in body["warning"]

    detector.next = FaceAnalysis(face_count=2, bbox=(0, 0, 10, 10),
                                 face_crop=np.zeros((10, 10, 3), np.uint8), detection_scores=[0.9, 0.7])
    body = post_frame(client, student_headers, started_exam, jpeg_bytes).json()
    assert body["face_count"] == 2 and "More than one face" in body["warning"]
    assert body["confidence"] == pytest.approx(0.7)
    types = sorted(i.incident_type.value for i in db.query(ProctoringIncident))
    assert types == ["multiple_faces", "no_face"]


def test_face_8b_model_missing_degrades_gracefully(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """FACE-8: without a loaded model the face check still runs and no gaze incident is raised."""
    _, gaze, _ = fakes
    gaze._loaded = False
    body = post_frame(client, student_headers, started_exam, jpeg_bytes).json()
    assert body["face_detected"] and body["gaze"] is None and body["warning"] is None


def test_int_2_multipart_upload_and_storage_failure(client, student_headers, started_exam, fakes, jpeg_bytes, db):
    """INT-2: multipart JPEG works; if MinIO fails the incident is still recorded."""
    _, gaze, storage = fakes
    gaze.prob_at = 0.05
    storage.fail = True
    r = client.post("/proctoring/frame", headers=student_headers,
                    data={"exam_id": str(started_exam)}, files={"file": ("f.jpg", jpeg_bytes, "image/jpeg")})
    assert r.status_code == 200, r.text
    incident = db.get(ProctoringIncident, r.json()["incident_id"])
    assert incident is not None and incident.evidence_key is None


def test_int_2b_bad_payloads(client, student_headers, started_exam, fakes):
    """INT-2: invalid images and payloads return 422; no exam in progress returns 409."""
    assert post_frame(client, student_headers, started_exam, b"not a jpeg").status_code == 422
    r = client.post("/proctoring/frame", headers=student_headers, json={"exam_id": started_exam, "image": "@@@"})
    assert r.status_code == 422
    r = client.post("/proctoring/frame", headers=student_headers, json={"image": "abc"})
    assert r.status_code == 422
    r = client.post("/proctoring/frame", headers=student_headers, data={"exam_id": str(started_exam)},
                    files={"other": ("f.jpg", b"x", "image/jpeg")})
    assert r.status_code == 422
    assert post_frame(client, student_headers, 9999, b"x").status_code == 409


def test_int_2c_frame_rejected_after_submit(client, student_headers, started_exam, fakes, jpeg_bytes):
    client.post(f"/exams/{started_exam}/submit", headers=student_headers)
    assert post_frame(client, student_headers, started_exam, jpeg_bytes).status_code == 409


def test_int_4_ml_runs_off_event_loop(client, student_headers, started_exam, fakes, jpeg_bytes):
    """INT-4: detection runs in the ML thread pool, not on the event loop thread."""
    detector, _, _ = fakes
    seen = {}
    original = detector.analyze

    def spy(image):
        seen["thread"] = threading.current_thread().name
        return original(image)

    detector.analyze = spy
    r = post_frame(client, student_headers, started_exam, jpeg_bytes)
    assert r.status_code == 200 and seen["thread"].startswith("ml")
    assert r.json()["processing_ms"] < 1000


def test_staff_cannot_post_frames(client, staff_headers, exam_id, jpeg_bytes):
    assert post_frame(client, staff_headers, exam_id, jpeg_bytes).status_code == 403


def test_deps_singletons():
    assert deps.get_face_detector() is deps.get_face_detector()
    assert deps.get_gaze_service() is deps.get_gaze_service()
    assert deps.get_gaze_service().loaded is False
