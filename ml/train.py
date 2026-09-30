"""Train one or all candidate gaze models. Run on a GPU (Colab/Kaggle/L4).

Usage:
  python ml/train.py --model efficientnetv2s
  python ml/train.py --model all --epochs 30
Best checkpoint per model -> ml/output/<model>.keras
Copy the chosen one to backend/models/gaze_model.keras.
"""
import argparse
import csv
import json

import cv2
import numpy as np
import tensorflow as tf

from architectures import ARCHITECTURES, PRETRAINED, unfreeze_top
from common import OUTPUT_DIR, SEED, SPLITS_DIR, preprocess_face
from losses import AsymmetricFocalLoss

tf.keras.utils.set_random_seed(SEED)
AUTOTUNE = tf.data.AUTOTUNE


def load_split(name: str):
    with open(SPLITS_DIR / f"{name}.csv") as f:
        rows = list(csv.DictReader(f))
    x = np.stack([preprocess_face(cv2.imread(r["path"])) for r in rows])
    y = np.array([int(r["label"]) for r in rows], dtype=np.float32)
    return x, y


def augment(image, label):
    image = tf.image.random_flip_left_right(image)
    image = tf.image.random_brightness(image, 0.2 * 255)
    image = tf.image.random_contrast(image, 0.7, 1.3)
    # small rotation (about +/-10 deg) via random affine
    angle = tf.random.uniform([], -0.17, 0.17)
    image = rotate(image, angle)
    return tf.clip_by_value(image, 0.0, 255.0), label


def rotate(image, angle):
    cos, sin = tf.cos(angle), tf.sin(angle)
    h = tf.cast(tf.shape(image)[0], tf.float32)
    w = tf.cast(tf.shape(image)[1], tf.float32)
    cx, cy = w / 2, h / 2
    transform = [cos, -sin, cx - cos * cx + sin * cy, sin, cos, cy - sin * cx - cos * cy, 0.0, 0.0]
    return tf.raw_ops.ImageProjectiveTransformV3(
        images=image[None], transforms=[transform], output_shape=tf.shape(image)[:2],
        interpolation="BILINEAR", fill_mode="REFLECT", fill_value=0.0)[0]


def make_dataset(x, y, batch, training):
    ds = tf.data.Dataset.from_tensor_slices((x, y))
    if training:
        # Oversample the minority class so it gets extra augmented views.
        counts = np.bincount(y.astype(int), minlength=2)
        minority = int(np.argmin(counts))
        factor = max(1, int(round(counts.max() / max(counts.min(), 1))) - 1)
        extra = tf.data.Dataset.from_tensor_slices((x[y == minority], y[y == minority])).repeat(factor)
        ds = ds.concatenate(extra).shuffle(len(x) * 2, seed=SEED).map(augment, num_parallel_calls=AUTOTUNE)
    return ds.batch(batch).prefetch(AUTOTUNE)


def class_weights(y):
    counts = np.bincount(y.astype(int), minlength=2)
    return {i: len(y) / (2.0 * max(c, 1)) for i, c in enumerate(counts)}


def compile_model(model, lr):
    model.compile(
        optimizer=tf.keras.optimizers.Adam(lr),
        loss=AsymmetricFocalLoss(alpha_at=0.4, gamma_at=2.0, alpha_away=0.6, gamma_away=2.0),
        metrics=["accuracy", tf.keras.metrics.AUC(name="auc"),
                 tf.keras.metrics.Precision(name="precision"), tf.keras.metrics.Recall(name="recall")],
    )


def callbacks(path):
    return [
        tf.keras.callbacks.ModelCheckpoint(str(path), monitor="val_auc", mode="max", save_best_only=True),
        tf.keras.callbacks.EarlyStopping(monitor="val_auc", mode="max", patience=6, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-7),
    ]


def train(name, data, epochs, batch):
    (x_tr, y_tr), (x_val, y_val) = data
    train_ds = make_dataset(x_tr, y_tr, batch, True)
    val_ds = make_dataset(x_val, y_val, batch, False)
    path = OUTPUT_DIR / f"{name}.keras"

    model = ARCHITECTURES[name]()
    compile_model(model, 1e-3 if name in PRETRAINED else 3e-4)
    # Class weights are redundant with oversampling for the training stream, but
    # keep a mild version to counter residual imbalance.
    cw = {k: v ** 0.5 for k, v in class_weights(y_tr).items()}
    hist = model.fit(train_ds, validation_data=val_ds, epochs=epochs, class_weight=cw, callbacks=callbacks(path))
    history = {k: [float(v) for v in vals] for k, vals in hist.history.items()}

    if name in PRETRAINED:  # stage 2: fine-tune top layers at a low LR
        unfreeze_top(model, 40)
        compile_model(model, 1e-5)
        hist2 = model.fit(train_ds, validation_data=val_ds, epochs=max(epochs // 2, 5),
                          class_weight=cw, callbacks=callbacks(path))
        for k, vals in hist2.history.items():
            history.setdefault(k, []).extend(float(v) for v in vals)

    (OUTPUT_DIR / f"{name}_history.json").write_text(json.dumps(history, indent=2))
    print(f"Saved best {name} to {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="efficientnetv2s", choices=[*ARCHITECTURES, "all"])
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=32)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    data = (load_split("train"), load_split("val"))
    for name in ARCHITECTURES if args.model == "all" else [args.model]:
        train(name, data, args.epochs, args.batch)


if __name__ == "__main__":
    main()
