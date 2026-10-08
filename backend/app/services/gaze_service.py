"""Gaze classifier: load once, preprocess, predict, adaptive threshold (thesis 4.3.6).

Mirrors the training notebook exactly:
  * model input is a 224x224 RGB face crop with raw 0-255 pixel values (the base
    network carries its own Rescaling layer, so no /255 here);
  * preprocessing = resize -> CLAHE on the L channel -> sharpen -> BGR->RGB;
  * the model outputs P(looking_at); "at" when prob > threshold.
"""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.services.face_detector import Orientation

log = logging.getLogger(__name__)

IMG_SIZE = (224, 224)
MIN_THRESHOLD_TILT = 0.2
MIN_THRESHOLD_OTHER = 0.15


def _load_keras_archive(tf, path: Path, custom_objects: dict):
    """Load a .keras archive without compiling, like load_model(compile=False), but fast.

    Keras 2.15 has h5py read model.weights.h5 straight from the zip. On Python 3.10 every
    backward seek in a zip member re-reads it from the start, so a 110 MB EfficientNetV2S
    took ~12 minutes. Extracting the weights to a real file first takes seconds.
    """
    with zipfile.ZipFile(path) as zf, tempfile.TemporaryDirectory() as tmp:
        config = json.loads(zf.read("config.json"))
        config.pop("compile_config", None)
        model = tf.keras.saving.deserialize_keras_object(config, custom_objects=custom_objects)
        model.load_weights(zf.extract("model.weights.h5", tmp))
    return model


def preprocess_face(face_bgr: np.ndarray) -> np.ndarray:
    import cv2

    face = cv2.resize(face_bgr, IMG_SIZE)
    lab = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    l_chan = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_chan)
    face = cv2.cvtColor(cv2.merge((l_chan, a_chan, b_chan)), cv2.COLOR_LAB2BGR)
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    face = cv2.filter2D(face, -1, kernel)
    face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
    return face.astype(np.float32)


def adjusted_threshold(base: float, orientation: Orientation | None) -> float:
    """Orientation-based adaptive threshold from the notebook's predict_gaze().

    Tilted, turned or smiling faces produced false "away" results, so the threshold
    for "looking at" is relaxed in those cases, never below the floors.
    """
    threshold = base
    if orientation is None:
        return threshold
    tilt = abs(orientation.tilt_degrees)
    if tilt > 10:
        reduction = 0.05 + (min(tilt, 30) - 10) / 20 * 0.15
        threshold = max(threshold - reduction, MIN_THRESHOLD_TILT)
    if orientation.eye_width_ratio < 0.85:
        threshold = max(threshold - 0.05, MIN_THRESHOLD_OTHER)
    if orientation.is_smiling:
        threshold = max(threshold - 0.08, MIN_THRESHOLD_OTHER)
    return threshold


@dataclass
class GazePrediction:
    gaze: str  # "at" | "away"
    prob_at: float
    confidence: float  # confidence in the predicted class
    threshold: float


def classify(prob_at: float, base_threshold: float, orientation: Orientation | None) -> GazePrediction:
    threshold = adjusted_threshold(base_threshold, orientation)
    looking_at = prob_at > threshold
    return GazePrediction(
        gaze="at" if looking_at else "away",
        prob_at=prob_at,
        confidence=prob_at if looking_at else 1.0 - prob_at,
        threshold=threshold,
    )


class GazeService:
    def __init__(self, model_path: str, base_threshold: float = 0.5):
        self.model_path = model_path
        self.base_threshold = base_threshold
        self.model = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> bool:
        path = Path(self.model_path)
        if not path.exists():
            log.warning("Gaze model not found at %s; gaze classification disabled", path)
            return False
        import tensorflow as tf

        from app.ml.losses import CUSTOM_OBJECTS

        if zipfile.is_zipfile(path):
            self.model = _load_keras_archive(tf, path, CUSTOM_OBJECTS)
        else:  # legacy .h5
            self.model = tf.keras.models.load_model(path, custom_objects=CUSTOM_OBJECTS, compile=False)
        # Warm up so the first real request is not slow.
        self.model(np.zeros((1, *IMG_SIZE, 3), dtype=np.float32), training=False)
        log.info("Loaded gaze model from %s", path)
        return True

    def predict_prob_at(self, face_bgr: np.ndarray) -> float:
        if self.model is None:
            raise RuntimeError("Gaze model not loaded")
        batch = np.expand_dims(preprocess_face(face_bgr), 0)
        with self._lock:
            out = self.model(batch, training=False)
        return float(np.asarray(out).reshape(-1)[0])

    def predict(self, face_bgr: np.ndarray, orientation: Orientation | None) -> GazePrediction:
        return classify(self.predict_prob_at(face_bgr), self.base_threshold, orientation)
