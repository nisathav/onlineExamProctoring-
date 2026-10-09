"""Shared test setup for the backend: uses a throwaway SQLite database, loads the demo data
before each test, and replaces the camera/AI/storage parts with fakes so tests run fast
without TensorFlow, MediaPipe or MinIO."""

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["LOGIN_RATE_LIMIT"] = "5"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.routes.auth import login_limiter  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import deps  # noqa: E402
from app.services.face_detector import FaceAnalysis, Orientation  # noqa: E402
from app.services.gaze_service import GazeService  # noqa: E402


class FakeDetector:
    """Returns whatever FaceAnalysis the test sets on `.next`."""

    def __init__(self):
        self.next = FaceAnalysis(
            face_count=1,
            bbox=(10, 10, 50, 50),
            face_crop=np.full((60, 60, 3), 128, np.uint8),
            orientation=Orientation(),
            detection_scores=[0.95],
        )

    def analyze(self, image):
        return self.next


class FakeGaze(GazeService):
    """Real thresholding logic, fixed model probability."""

    def __init__(self, prob_at=0.9, loaded=True):
        super().__init__("unused", 0.5)
        self.prob_at = prob_at
        self._loaded = loaded

    @property
    def loaded(self):
        return self._loaded

    def predict_prob_at(self, face_bgr):
        return self.prob_at


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.fail = False

    def put_jpeg(self, key, data):
        if self.fail:
            raise RuntimeError("minio down")
        self.objects[key] = data
        return key

    def presigned_url(self, key):
        return f"http://minio.test/evidence/{key}?X-Amz-Signature=abc"

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture
def jpeg_bytes():
    img = np.full((120, 160, 3), 200, np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


@pytest.fixture
def fakes():
    detector, gaze, storage = FakeDetector(), FakeGaze(), FakeStorage()
    app.dependency_overrides[deps.get_face_detector] = lambda: detector
    app.dependency_overrides[deps.get_gaze_service] = lambda: gaze
    app.dependency_overrides[deps.get_storage] = lambda: storage
    yield detector, gaze, storage
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def db_setup():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    login_limiter.reset()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(fakes):
    with TestClient(app) as c:
        yield c


def login(client, username, password):
    r = client.post("/auth/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def staff_headers(client):
    return login(client, "staff1", "staffpass123")


@pytest.fixture
def student_headers(client):
    return login(client, "student1", "studentpass123")


@pytest.fixture
def exam_id(client, staff_headers):
    return client.get("/exams", headers=staff_headers).json()[0]["id"]


@pytest.fixture
def started_exam(client, student_headers, exam_id):
    """Student has consented and started the seeded exam."""
    assert client.post("/auth/consent", headers=student_headers).status_code == 200
    r = client.post(f"/exams/{exam_id}/start", headers=student_headers)
    assert r.status_code == 200, r.text
    return exam_id
