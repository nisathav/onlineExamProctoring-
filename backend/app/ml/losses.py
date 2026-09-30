"""Asymmetric focal loss shared by training (ml/) and inference (backend).

Label convention (matches the training notebook): 1 = looking_at, 0 = looking_away,
so the model outputs P(looking_at). The "away" class gets its own alpha/gamma so the
minority class can be emphasised independently.

The model must be loaded with this loss as a custom object, e.g.
    tf.keras.models.load_model(path, custom_objects=CUSTOM_OBJECTS)
"""
import tensorflow as tf


@tf.keras.utils.register_keras_serializable(package="proctoring")
class AsymmetricFocalLoss(tf.keras.losses.Loss):
    def __init__(
        self,
        alpha_at: float = 0.5,
        gamma_at: float = 2.0,
        alpha_away: float = 0.5,
        gamma_away: float = 2.0,
        name: str = "asymmetric_focal_loss",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self.alpha_at = alpha_at
        self.gamma_at = gamma_at
        self.alpha_away = alpha_away
        self.gamma_away = gamma_away

    def call(self, y_true, y_pred):
        y_true = tf.cast(y_true, tf.float32)
        y_pred = tf.clip_by_value(tf.cast(y_pred, tf.float32), 1e-7, 1.0 - 1e-7)
        y_true = tf.reshape(y_true, tf.shape(y_pred))

        bce = -(y_true * tf.math.log(y_pred) + (1.0 - y_true) * tf.math.log(1.0 - y_pred))
        p_t = y_true * y_pred + (1.0 - y_true) * (1.0 - y_pred)
        alpha = y_true * self.alpha_at + (1.0 - y_true) * self.alpha_away
        gamma = y_true * self.gamma_at + (1.0 - y_true) * self.gamma_away
        return alpha * tf.pow(1.0 - p_t, gamma) * bce

    def get_config(self):
        config = super().get_config()
        config.update(
            alpha_at=self.alpha_at,
            gamma_at=self.gamma_at,
            alpha_away=self.alpha_away,
            gamma_away=self.gamma_away,
        )
        return config


@tf.keras.utils.register_keras_serializable(package="proctoring")
def balanced_asymmetric_focal_loss(y_true, y_pred, alpha=0.5, gamma=2.0):
    """Function form used in the original notebook (kept so old checkpoints load)."""
    y_pred = tf.clip_by_value(tf.convert_to_tensor(y_pred, tf.float32), 1e-7, 1.0 - 1e-7)
    y_true = tf.cast(y_true, tf.float32)
    bce = tf.keras.backend.binary_crossentropy(y_true, y_pred)
    p_t = y_true * y_pred + (1 - y_true) * (1 - y_pred)
    asymmetric_alpha = y_true * (1 - alpha) + (1 - y_true) * alpha
    return tf.reduce_mean(asymmetric_alpha * tf.pow(1 - p_t, gamma) * bce)


CUSTOM_OBJECTS = {
    "AsymmetricFocalLoss": AsymmetricFocalLoss,
    "asymmetric_focal_loss": AsymmetricFocalLoss,
    "balanced_asymmetric_focal_loss": balanced_asymmetric_focal_loss,
}
