"""Five candidate gaze classifiers (thesis 3.3.4, Table 5.1).

All models take a 224x224x3 RGB face with raw 0-255 pixels and output P(looking_at).
Pretrained bases include their own rescaling; the custom CNNs get a Rescaling layer
so every model accepts the same input as the backend sends.
"""
import tensorflow as tf
from tensorflow.keras import Model, layers

INPUT_SHAPE = (224, 224, 3)


def _head(x, dropout=(0.5, 0.4)):
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(dropout[0])(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(dropout[1])(x)
    return layers.Dense(1, activation="sigmoid", name="p_looking_at")(x)


def basic_cnn() -> Model:
    inputs = layers.Input(INPUT_SHAPE)
    x = layers.Rescaling(1.0 / 255)(inputs)
    for filters in (32, 64, 128):
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D()(x)
    return Model(inputs, _head(x), name="basic_cnn")


def mobilenetv3_transfer() -> Model:
    inputs = layers.Input(INPUT_SHAPE)
    base = tf.keras.applications.MobileNetV3Small(
        input_tensor=inputs, include_top=False, weights="imagenet")
    base.trainable = False
    return Model(inputs, _head(base.output), name="mobilenetv3_transfer")


def efficientnetv2s_transfer() -> Model:
    """Thesis choice. Base frozen for stage 1; call unfreeze_top() for fine-tuning."""
    inputs = layers.Input(INPUT_SHAPE)
    base = tf.keras.applications.EfficientNetV2S(
        input_tensor=inputs, include_top=False, weights="imagenet", include_preprocessing=True)
    base.trainable = False
    return Model(inputs, _head(base.output), name="efficientnetv2s_transfer")


def attention_cnn() -> Model:
    """Custom CNN with a spatial attention map (as in the notebook's balanced model)."""
    inputs = layers.Input(INPUT_SHAPE)
    x = layers.Rescaling(1.0 / 255)(inputs)
    for filters in (32, 64, 128, 256):
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D()(x)
    attn = layers.Conv2D(64, 1, activation="relu")(x)
    attn = layers.Conv2D(1, 1, activation="sigmoid", name="spatial_attention")(attn)
    x = layers.Multiply()([x, attn])
    return Model(inputs, _head(x), name="attention_cnn")


def cnn_ensemble(n_members: int = 3) -> Model:
    """Average of small CNNs with different kernel sizes."""
    inputs = layers.Input(INPUT_SHAPE)
    scaled = layers.Rescaling(1.0 / 255)(inputs)
    outputs = []
    for i, k in enumerate((3, 5, 7)[:n_members]):
        x = scaled
        for filters in (32, 64, 128):
            x = layers.Conv2D(filters, k, padding="same", activation="relu")(x)
            x = layers.MaxPooling2D()(x)
        x = layers.GlobalAveragePooling2D()(x)
        x = layers.Dense(64, activation="relu")(x)
        outputs.append(layers.Dense(1, activation="sigmoid", name=f"member_{i}")(x))
    return Model(inputs, layers.Average(name="p_looking_at")(outputs), name="cnn_ensemble")


def unfreeze_top(model: Model, n_layers: int = 40) -> None:
    """Unfreeze the top `n_layers` of the pretrained base (BatchNorm stays frozen)."""
    for layer in model.layers:
        if isinstance(layer, Model):  # the pretrained base
            layer.trainable = True
            for sub in layer.layers[:-n_layers]:
                sub.trainable = False
            for sub in layer.layers:
                if isinstance(sub, layers.BatchNormalization):
                    sub.trainable = False


ARCHITECTURES = {
    "basic_cnn": basic_cnn,
    "mobilenetv3": mobilenetv3_transfer,
    "efficientnetv2s": efficientnetv2s_transfer,
    "attention_cnn": attention_cnn,
    "ensemble": cnn_ensemble,
}
PRETRAINED = {"mobilenetv3", "efficientnetv2s"}
