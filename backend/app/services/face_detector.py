"""MediaPipe face detection + head-orientation estimate (thesis 4.2.2, notebook cells 4-8, 22).

MediaPipe solution objects are not thread-safe, so each worker thread gets its own
instances via threading.local. Pure geometry lives in `orientation_from_landmarks`
so it can be unit-tested without MediaPipe.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field

import numpy as np

# Face-mesh landmark indices used by the notebook's predict_gaze()
LEFT_EYE_OUTER, LEFT_EYE_INNER = 33, 133
RIGHT_EYE_OUTER, RIGHT_EYE_INNER = 263, 362
MOUTH_LEFT, MOUTH_RIGHT, MOUTH_TOP, MOUTH_BOTTOM = 61, 291, 0, 17
FACE_MARGIN = 0.2  # 20% margin around the detected box, as in extract_face()


@dataclass
class Orientation:
    tilt_degrees: float = 0.0
    eye_width_ratio: float = 1.0  # min/max eye width; < 0.85 suggests a turned head
    smile_ratio: float = 0.0  # mouth width / mouth height

    @property
    def is_smiling(self) -> bool:
        return self.smile_ratio > 4.0


@dataclass
class FaceAnalysis:
    face_count: int
    bbox: tuple[int, int, int, int] | None = None  # x, y, w, h of the largest face
    face_crop: np.ndarray | None = None  # BGR crop with margin
    orientation: Orientation | None = None
    detection_scores: list[float] = field(default_factory=list)


def orientation_from_landmarks(points: dict[int, tuple[float, float]]) -> Orientation:
    """Compute tilt, eye symmetry and smile ratio from pixel-space landmark points."""
    lx, ly = points[LEFT_EYE_OUTER]
    rx, ry = points[RIGHT_EYE_OUTER]
    tilt = math.degrees(math.atan2(ry - ly, rx - lx))

    left_w = abs(points[LEFT_EYE_OUTER][0] - points[LEFT_EYE_INNER][0])
    right_w = abs(points[RIGHT_EYE_OUTER][0] - points[RIGHT_EYE_INNER][0])
    biggest = max(left_w, right_w)
    eye_ratio = (min(left_w, right_w) / biggest) if biggest > 0 else 1.0

    mouth_w = abs(points[MOUTH_RIGHT][0] - points[MOUTH_LEFT][0])
    mouth_h = abs(points[MOUTH_BOTTOM][1] - points[MOUTH_TOP][1])
    smile = mouth_w / max(mouth_h, 1.0)
    return Orientation(tilt_degrees=tilt, eye_width_ratio=eye_ratio, smile_ratio=smile)


def crop_with_margin(image: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = bbox
    mx, my = int(w * FACE_MARGIN), int(h * FACE_MARGIN)
    img_h, img_w = image.shape[:2]
    x1, y1 = max(0, x - mx), max(0, y - my)
    x2, y2 = min(img_w, x + w + mx), min(img_h, y + h + my)
    return image[y1:y2, x1:x2]


class FaceDetector:
    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence
        self._local = threading.local()

    def _solutions(self):
        if not hasattr(self._local, "detector"):
            import mediapipe as mp

            self._local.detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=self.min_confidence
            )
            self._local.mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True, max_num_faces=1, min_detection_confidence=self.min_confidence
            )
        return self._local.detector, self._local.mesh

    def analyze(self, image_bgr: np.ndarray) -> FaceAnalysis:
        import cv2

        detector, mesh = self._solutions()
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        result = detector.process(rgb)
        if not result.detections:
            return FaceAnalysis(face_count=0)

        h, w = image_bgr.shape[:2]
        boxes, scores = [], []
        for det in result.detections:
            rb = det.location_data.relative_bounding_box
            boxes.append((int(rb.xmin * w), int(rb.ymin * h), int(rb.width * w), int(rb.height * h)))
            scores.append(float(det.score[0]) if det.score else 0.0)
        bbox = max(boxes, key=lambda b: b[2] * b[3])

        orientation = None
        mesh_result = mesh.process(rgb)
        if mesh_result.multi_face_landmarks:
            lm = mesh_result.multi_face_landmarks[0].landmark
            idx = [LEFT_EYE_OUTER, LEFT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_EYE_INNER,
                   MOUTH_LEFT, MOUTH_RIGHT, MOUTH_TOP, MOUTH_BOTTOM]
            orientation = orientation_from_landmarks({i: (lm[i].x * w, lm[i].y * h) for i in idx})

        return FaceAnalysis(
            face_count=len(boxes),
            bbox=bbox,
            face_crop=crop_with_margin(image_bgr, bbox),
            orientation=orientation,
            detection_scores=scores,
        )
