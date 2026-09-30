"""Compare trained models on the test split (Table 5.1).

For each ml/output/<model>.keras: accuracy, per-class precision/recall/F1, ROC AUC,
mean inference time per sample, plus the best threshold found on the validation set.
Writes ml/output/comparison.{csv,md} and a confusion matrix PNG per model.

Choose the model on macro F1 + AUC, not looking-away recall alone: a model that
predicts "away" for everything gets 100% away recall and is useless.
"""
import csv
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import tensorflow as tf  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    ConfusionMatrixDisplay,
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from architectures import ARCHITECTURES  # noqa: E402
from common import CLASSES, OUTPUT_DIR  # noqa: E402
from losses import CUSTOM_OBJECTS  # noqa: E402
from train import load_split  # noqa: E402


def best_threshold(y, prob):
    grid = np.round(np.arange(0.1, 0.91, 0.05), 2)
    scores = [f1_score(y, (prob > t).astype(int), average="macro", zero_division=0) for t in grid]
    return float(grid[int(np.argmax(scores))])


def time_per_sample(model, x, n=50):
    sample = x[:1]
    model(sample, training=False)  # warm-up
    start = time.perf_counter()
    for i in range(n):
        model(x[i % len(x):i % len(x) + 1], training=False)
    return (time.perf_counter() - start) / n * 1000


def evaluate(name, x_val, y_val, x_test, y_test):
    model = tf.keras.models.load_model(OUTPUT_DIR / f"{name}.keras", custom_objects=CUSTOM_OBJECTS, compile=False)
    val_prob = model.predict(x_val, verbose=0).ravel()
    prob = model.predict(x_test, verbose=0).ravel()
    tuned = best_threshold(y_val, val_prob)
    row = {"model": name, "tuned_threshold": tuned}
    for label, t in [("@0.5", 0.5), ("@tuned", tuned)]:
        pred = (prob > t).astype(int)
        p, r, f, _ = precision_recall_fscore_support(y_test, pred, labels=[0, 1], zero_division=0)
        row[f"accuracy{label}"] = accuracy_score(y_test, pred)
        row[f"macro_f1{label}"] = f1_score(y_test, pred, average="macro", zero_division=0)
        for i, cls in enumerate(CLASSES):
            row[f"{cls}_precision{label}"] = p[i]
            row[f"{cls}_recall{label}"] = r[i]
            row[f"{cls}_f1{label}"] = f[i]
        if label == "@0.5":
            cm = confusion_matrix(y_test, pred, labels=[0, 1])
            ConfusionMatrixDisplay(cm, display_labels=CLASSES).plot(cmap="Blues", colorbar=False)
            plt.title(f"{name} (threshold 0.5)")
            plt.tight_layout()
            plt.savefig(OUTPUT_DIR / f"{name}_confusion.png", dpi=120)
            plt.close()
    row["roc_auc"] = roc_auc_score(y_test, prob) if len(set(y_test)) > 1 else float("nan")
    row["ms_per_sample"] = time_per_sample(model, x_test)
    return row


def main():
    x_val, y_val = load_split("val")
    x_test, y_test = load_split("test")
    rows = [evaluate(n, x_val, y_val, x_test, y_test)
            for n in ARCHITECTURES if (OUTPUT_DIR / f"{n}.keras").exists()]
    if not rows:
        raise SystemExit("No trained models in ml/output/")

    with open(OUTPUT_DIR / "comparison.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    cols = ["model", "accuracy@0.5", "looking_at_f1@0.5", "looking_away_f1@0.5",
            "looking_away_recall@0.5", "macro_f1@0.5", "roc_auc", "ms_per_sample", "tuned_threshold"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in sorted(rows, key=lambda r: (-r["macro_f1@0.5"], -r["roc_auc"])):
        lines.append("| " + " | ".join(
            r[c] if isinstance(r[c], str) else f"{r[c]:.3f}" for c in cols) + " |")
    (OUTPUT_DIR / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
