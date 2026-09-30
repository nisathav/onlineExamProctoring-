"""Crop faces with MediaPipe and write a stratified 80/15/5 train/val/test split.

Input:  ml/data/{looking_at,looking_away}/*.jpg|png  (AFLW2000-3D / Multi-PIE, labelled)
Output: ml/data/faces/<class>/<name>.png   (224x224 face crops, BGR, not yet preprocessed)
        ml/splits/{train,val,test}.csv     (path,label)

Usage: python ml/prepare_data.py [--data-dir ml/data]
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

import cv2
import mediapipe as mp
from sklearn.model_selection import train_test_split

from common import CLASSES, DATA_DIR, IMG_SIZE, SEED, SPLITS_DIR, crop_with_margin

EXTS = {".jpg", ".jpeg", ".png"}


def crop_face(detector, image):
    result = detector.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    if not result.detections:
        return None
    h, w = image.shape[:2]
    boxes = []
    for det in result.detections:
        rb = det.location_data.relative_bounding_box
        boxes.append((int(rb.xmin * w), int(rb.ymin * h), int(rb.width * w), int(rb.height * h)))
    crop = crop_with_margin(image, max(boxes, key=lambda b: b[2] * b[3]))
    return cv2.resize(crop, IMG_SIZE) if crop.size else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()

    faces_dir = args.data_dir / "faces"
    paths, labels, failures = [], [], []
    with mp.solutions.face_detection.FaceDetection(min_detection_confidence=0.5) as detector:
        for label, cls in enumerate(CLASSES):
            out_dir = faces_dir / cls
            out_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted((args.data_dir / cls).glob("*")):
                if src.suffix.lower() not in EXTS:
                    continue
                image = cv2.imread(str(src))
                face = crop_face(detector, image) if image is not None else None
                if face is None:
                    failures.append(src)
                    continue
                dst = out_dir / f"{src.stem}.png"
                cv2.imwrite(str(dst), face)
                paths.append(str(dst))
                labels.append(label)

    if not paths:
        raise SystemExit(f"No faces found under {args.data_dir}/{{{','.join(CLASSES)}}}")

    # 80 / 15 / 5 stratified split
    train_p, rest_p, train_y, rest_y = train_test_split(
        paths, labels, test_size=0.20, stratify=labels, random_state=SEED)
    val_p, test_p, val_y, test_y = train_test_split(
        rest_p, rest_y, test_size=0.25, stratify=rest_y, random_state=SEED)

    SPLITS_DIR.mkdir(exist_ok=True)
    for name, ps, ys in [("train", train_p, train_y), ("val", val_p, val_y), ("test", test_p, test_y)]:
        with open(SPLITS_DIR / f"{name}.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["path", "label"])
            writer.writerows(zip(ps, ys))
        counts = Counter(ys)
        print(f"{name:5s} n={len(ys):5d}  " + "  ".join(f"{CLASSES[k]}={counts.get(k, 0)}" for k in range(2)))
    print(f"Face detection failed on {len(failures)} images")


if __name__ == "__main__":
    main()
