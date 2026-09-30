"""Convert the Colab notebook's .h5 checkpoint to a .keras file the backend can load.

The notebook trained with TensorFlow 2.17 / Keras 3, so its .h5 files cannot be
deserialised by the backend's TensorFlow 2.15.1 (Keras 2). This script rebuilds the
notebook's `build_balanced_model()` architecture in Keras 2 (MobileNetV3Small +
spatial attention head, 224x224 RGB raw 0-255 input, output P(looking_at)) and copies
the weights across layer by layer, checking every shape.

Usage (with the backend's TF 2.15.1 environment):
  python ml/convert_notebook_model.py improved_gaze_detection_model.h5 \
      backend/models/gaze_model.keras
"""
import argparse

import h5py
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers


def build_balanced_model() -> tf.keras.Model:
    """Architecture from notebook cell 14 (build_balanced_model)."""
    inputs = layers.Input(shape=(224, 224, 3))
    base = tf.keras.applications.MobileNetV3Small(input_tensor=inputs, include_top=False, weights=None)
    x = base.output
    attention = layers.Conv2D(128, (1, 1), activation="relu")(x)
    attention = layers.Conv2D(1, (1, 1), activation="sigmoid")(attention)
    x = layers.Multiply()([x, attention])
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dense(512, activation="relu")(x)
    x = layers.Dropout(0.5)(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(0.4)(x)
    outputs = layers.Dense(1, activation="sigmoid")(x)
    return tf.keras.Model(inputs, outputs)


def _decode(values):
    return [v.decode() if isinstance(v, bytes) else v for v in values]


def read_h5_weights(path: str) -> list[tuple[str, list[np.ndarray]]]:
    """Weighted layers in model order, each with its arrays in saved order."""
    with h5py.File(path, "r") as f:
        group = f["model_weights"] if "model_weights" in f else f
        result = []
        for name in _decode(group.attrs["layer_names"]):
            weight_names = _decode(group[name].attrs["weight_names"])
            if weight_names:
                result.append((name, [group[name][w][()] for w in weight_names]))
        return result


def convert(src: str) -> tf.keras.Model:
    model = build_balanced_model()
    targets = [layer for layer in model.layers if layer.weights]
    sources = read_h5_weights(src)
    if len(targets) != len(sources):
        raise SystemExit(f"Layer count mismatch: model {len(targets)} vs file {len(sources)}")
    for layer, (src_name, arrays) in zip(targets, sources):
        expected = [tuple(w.shape) for w in layer.weights]
        got = [a.shape for a in arrays]
        if expected != got:
            raise SystemExit(f"Shape mismatch at {layer.name} <- {src_name}: {expected} vs {got}")
        layer.set_weights(arrays)
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    args = parser.parse_args()

    model = convert(args.src)
    model.save(args.dst)
    prob = float(model(np.zeros((1, 224, 224, 3), np.float32), training=False)[0][0])
    print(f"Saved {args.dst} (P(looking_at) on a black frame = {prob:.4f})")


if __name__ == "__main__":
    main()
