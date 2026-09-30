"""Convert the Colab notebook's .h5 checkpoint to the .keras format the backend expects.

The notebook (Enhanced_Proctoring_with_Gaze) saves `improved_gaze_detection_model.h5`:
MobileNetV3Small + attention head, 224x224 RGB raw 0-255 input, output P(looking_at).
That matches the backend's preprocessing, so it can be served as-is.

Usage: python ml/convert_notebook_model.py improved_gaze_detection_model.h5 \
           backend/models/gaze_model.keras
"""
import argparse

import numpy as np
import tensorflow as tf

from losses import CUSTOM_OBJECTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    args = parser.parse_args()

    model = tf.keras.models.load_model(args.src, custom_objects=CUSTOM_OBJECTS, compile=False)
    if tuple(model.input_shape[1:]) != (224, 224, 3) or model.output_shape[-1] != 1:
        raise SystemExit(f"Unexpected model shape {model.input_shape} -> {model.output_shape}")
    prob = float(model(np.zeros((1, 224, 224, 3), np.float32), training=False)[0][0])
    model.save(args.dst)
    print(f"Saved {args.dst} (sanity P(looking_at) on a black frame = {prob:.3f})")


if __name__ == "__main__":
    main()
