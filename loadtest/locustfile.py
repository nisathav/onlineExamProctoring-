"""Phase 9 load test (NFR1): N students logging in and posting a frame every 3 s.

Prerequisites: the backend is running and the students exist and have consented.
Create them with:  python loadtest/create_students.py --count 100

Run headless at 25/50/100 users and record p50/p95 latency + error rate:
  locust -f loadtest/locustfile.py --host http://localhost:8000 --headless \
         -u 100 -r 10 -t 3m --csv loadtest/results/u100
"""
import base64
import itertools
import os
from pathlib import Path

from locust import HttpUser, between, events, task

PASSWORD = os.getenv("LOAD_PASSWORD", "loadtest-pass-123")
EXAM_ID = int(os.getenv("LOAD_EXAM_ID", "1"))
FRAME_PATH = Path(os.getenv("LOAD_FRAME", Path(__file__).with_name("sample_frame.jpg")))
_counter = itertools.count(1)


def _frame_b64() -> str:
    if FRAME_PATH.exists():
        return base64.b64encode(FRAME_PATH.read_bytes()).decode()
    import cv2  # fallback: a synthetic 640x480 JPEG, similar size to a webcam frame
    import numpy as np

    img = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    return base64.b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()).decode()


FRAME = _frame_b64()


class Student(HttpUser):
    wait_time = between(3, 3)  # thesis capture interval

    def on_start(self):
        username = f"load{next(_counter):03d}"
        r = self.client.post("/auth/token", data={"username": username, "password": PASSWORD}, name="/auth/token")
        r.raise_for_status()
        self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        self.client.post(f"/exams/{EXAM_ID}/start", name="/exams/[id]/start")

    @task
    def send_frame(self):
        self.client.post("/proctoring/frame", json={"exam_id": EXAM_ID, "image": FRAME}, name="/proctoring/frame")


@events.quitting.add_listener
def _summary(environment, **_):
    stats = environment.stats.get("/proctoring/frame", "POST")
    if stats.num_requests:
        print(f"\n/proctoring/frame  n={stats.num_requests}  p50={stats.get_response_time_percentile(0.5):.0f}ms  "
              f"p95={stats.get_response_time_percentile(0.95):.0f}ms  errors={stats.fail_ratio:.2%}")
