"""Frame analysis pipeline: decode -> face detection -> gaze -> decision.

`analyze_frame` is CPU-bound and synchronous; route handlers run it in the ML
thread pool (see app.services.deps.run_ml).
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

import numpy as np

from app.models import IncidentType
from app.services.face_detector import FaceDetector
from app.services.gaze_service import GazeService

WARNINGS = {
    IncidentType.no_face: "No face detected. Please stay in view of your camera.",
    IncidentType.multiple_faces: "More than one face detected. Only you should be visible.",
    IncidentType.looking_away: "You appear to be looking away from the screen.",
}


class InvalidImage(ValueError):
    pass


def decode_base64_image(data: str) -> bytes:
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImage("image is not valid base64") from exc


def bytes_to_bgr(raw: bytes) -> np.ndarray:
    import cv2

    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR) if arr.size else None
    if img is None:
        raise InvalidImage("could not decode image as JPEG/PNG")
    return img


@dataclass
class FrameDecision:
    face_detected: bool
    face_count: int
    gaze: str | None
    confidence: float
    incident_type: IncidentType | None

    @property
    def warning(self) -> str | None:
        return WARNINGS.get(self.incident_type) if self.incident_type else None


def analyze_frame(raw: bytes, detector: FaceDetector, gaze: GazeService) -> FrameDecision:
    image = bytes_to_bgr(raw)
    analysis = detector.analyze(image)

    if analysis.face_count == 0:
        return FrameDecision(False, 0, None, 1.0, IncidentType.no_face)
    if analysis.face_count > 1:
        conf = min(analysis.detection_scores) if analysis.detection_scores else 1.0
        return FrameDecision(True, analysis.face_count, None, conf, IncidentType.multiple_faces)

    if not gaze.loaded or analysis.face_crop is None or analysis.face_crop.size == 0:
        # Face present but no classifier available: nothing to flag.
        return FrameDecision(True, 1, None, 0.0, None)

    pred = gaze.predict(analysis.face_crop, analysis.orientation)
    incident = IncidentType.looking_away if pred.gaze == "away" else None
    return FrameDecision(True, 1, pred.gaze, round(pred.confidence, 4), incident)
