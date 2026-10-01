"""Real TensorFlow / MediaPipe / MinIO-client paths (skipped when the libs are absent).

INT-5: model saved with the focal loss round-trips through GazeService.load().
FACE-9: MediaPipe detector runs on real images from several threads.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pytest

from app.core.config import Settings


@pytest.fixture(scope="module")
def tf():
    return pytest.importorskip("tensorflow")


def _tiny_model(tf, loss):
    inputs = tf.keras.layers.Input((224, 224, 3))
    x = tf.keras.layers.Rescaling(1.0 / 255)(inputs)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid")(x)
    model = tf.keras.Model(inputs, outputs)
    model.compile(optimizer="adam", loss=loss)
    return model


def test_int_5_focal_loss_values(tf):
    """INT-5: focal loss down-weights easy examples and is serialisable."""
    from app.ml.losses import AsymmetricFocalLoss, balanced_asymmetric_focal_loss

    loss = AsymmetricFocalLoss(alpha_at=0.4, alpha_away=0.6)
    y = tf.constant([[1.0], [0.0]])
    easy = float(loss(y, tf.constant([[0.95], [0.05]])))
    hard = float(loss(y, tf.constant([[0.3], [0.7]])))
    assert 0 <= easy < hard
    assert AsymmetricFocalLoss.from_config(loss.get_config()).alpha_away == 0.6
    assert float(balanced_asymmetric_focal_loss(y, tf.constant([[0.9], [0.1]]))) >= 0


@pytest.mark.parametrize("suffix", [".keras", ".h5"])
def test_int_5_model_round_trip_with_custom_loss(tf, tmp_path, suffix):
    """INT-5: a model compiled with the focal loss loads in GazeService and predicts."""
    from app.ml.losses import AsymmetricFocalLoss
    from app.services.face_detector import Orientation
    from app.services.gaze_service import GazeService

    path = tmp_path / f"gaze_model{suffix}"
    _tiny_model(tf, AsymmetricFocalLoss()).save(path)

    service = GazeService(str(path), 0.5)
    assert service.load() and service.loaded
    face = np.random.default_rng(1).integers(0, 255, (150, 120, 3), dtype=np.uint8)
    prob = service.predict_prob_at(face)
    assert 0.0 <= prob <= 1.0
    pred = service.predict(face, Orientation(tilt_degrees=20))
    assert pred.gaze in ("at", "away") and pred.threshold == pytest.approx(0.375)


def test_gaze_service_missing_model(tmp_path):
    from app.services.gaze_service import GazeService

    service = GazeService(str(tmp_path / "nope.keras"))
    assert service.load() is False and not service.loaded
    with pytest.raises(RuntimeError):
        service.predict_prob_at(np.zeros((10, 10, 3), np.uint8))


def test_face_9_mediapipe_detector_threads():
    """FACE-9: real MediaPipe on blank frames -> no face; safe across worker threads."""
    pytest.importorskip("mediapipe")
    from app.services.face_detector import FaceDetector

    detector = FaceDetector()
    blank = np.full((480, 640, 3), 30, np.uint8)
    with ThreadPoolExecutor(3) as pool:
        results = list(pool.map(detector.analyze, [blank] * 6))
    assert all(r.face_count == 0 and r.bbox is None for r in results)


def test_face_9b_analyze_frame_end_to_end_without_model():
    """FACE-9: JPEG bytes -> MediaPipe -> no_face decision."""
    pytest.importorskip("mediapipe")
    import cv2

    from app.models import IncidentType
    from app.services.face_detector import FaceDetector
    from app.services.gaze_service import GazeService
    from app.services.proctoring import analyze_frame

    ok, buf = cv2.imencode(".jpg", np.full((240, 320, 3), 90, np.uint8))
    decision = analyze_frame(buf.tobytes(), FaceDetector(), GazeService("missing.keras"))
    assert decision.incident_type == IncidentType.no_face and decision.warning


def test_presigned_url_uses_public_endpoint_offline():
    """Presigned evidence URLs point at the browser-facing host and expire."""
    pytest.importorskip("minio")
    from app.services.storage import EvidenceStorage, evidence_key

    storage = EvidenceStorage(Settings(
        minio_endpoint="minio:9000", minio_public_endpoint="exam.example.com",
        minio_public_secure=True, presigned_url_expiry_seconds=120,
    ))
    key = evidence_key("student1", 3, datetime(2025, 1, 1, tzinfo=timezone.utc))
    url = storage.presigned_url(key)
    assert url.startswith("https://exam.example.com/evidence/student1/3/")
    assert "X-Amz-Expires=120" in url and "X-Amz-Signature=" in url


def test_int_6_notebook_h5_conversion(tf, tmp_path):
    """INT-6: ml/convert_notebook_model.py copies notebook weights exactly and the result serves."""
    import sys
    from pathlib import Path

    # repo-root ml/ on the host; mounted at /app/ml in the backend container
    here = Path(__file__).resolve()
    candidates = (here.parents[2] / "ml", here.parents[1] / "ml")
    ml_dir = next((d for d in candidates if (d / "convert_notebook_model.py").exists()), None)
    if ml_dir is None:
        pytest.skip("ml/convert_notebook_model.py not available")
    sys.path.insert(0, str(ml_dir))
    import convert_notebook_model as conv

    from app.services.gaze_service import GazeService

    original = conv.build_balanced_model()
    rng = np.random.default_rng(3)
    # small perturbation keeps BatchNorm variances positive
    original.set_weights([(w + rng.normal(0, 0.01, w.shape)).astype("float32") for w in original.get_weights()])
    src = tmp_path / "notebook.h5"
    original.save(src)

    converted = conv.convert(str(src))
    batch = rng.integers(0, 255, (2, 224, 224, 3)).astype("float32")
    np.testing.assert_allclose(converted(batch).numpy(), original(batch).numpy(), atol=1e-6)

    dst = tmp_path / "gaze_model.keras"
    converted.save(dst)
    service = GazeService(str(dst))
    assert service.load()
    assert 0.0 <= service.predict_prob_at(np.zeros((100, 100, 3), np.uint8)) <= 1.0
