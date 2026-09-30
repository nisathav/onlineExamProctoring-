"""Shared helpers for the training scripts. Face crop/preprocess must match the backend."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

# Reuse the exact inference preprocessing so training and serving never drift.
from app.services.face_detector import crop_with_margin  # noqa: E402,F401
from app.services.gaze_service import IMG_SIZE, preprocess_face  # noqa: E402,F401

DATA_DIR = ROOT / "data"
SPLITS_DIR = ROOT / "splits"
OUTPUT_DIR = ROOT / "output"
CLASSES = ["looking_away", "looking_at"]  # index == label; model outputs P(looking_at)
SEED = 42
