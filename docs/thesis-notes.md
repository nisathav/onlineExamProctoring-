# Thesis notes and implementation decisions

Paste the relevant thesis sections (4.2.x, 4.3.x, Appendix B) below so that future Claude Code sessions can reference them. The decisions below record where the code follows the training notebook (`Enhanced_Proctoring_with_Gaze_FIXED.ipynb`) and where it deliberately differs.

## Followed from the notebook

- **Face crop:** MediaPipe face detection (min confidence 0.5), largest face, 20% margin.
- **Preprocessing:** resize to 224×224, CLAHE (clip 2.0, 8×8) on the LAB L channel, 3×3 sharpen, BGR→RGB, **no /255** (the base network rescales internally).
- **Labels:** 1 = looking_at, 0 = looking_away; the model outputs P(looking_at).
- **Adaptive threshold** (`predict_gaze`): base 0.5; tilt over 10° lowers it by `0.05 + (min(|tilt|,30)-10)/20 × 0.15` (floor 0.2); eye-width ratio below 0.85 lowers it by 0.05, and a smile ratio above 4 lowers it by 0.08 (floor 0.15).
- **Asymmetric focal loss:** `balanced_asymmetric_focal_loss` is kept for loading old checkpoints. `AsymmetricFocalLoss` adds a separate alpha/gamma per class.

## Differences and additions

- **Notebook model file:** saved with Keras 3.15.1, which TF 2.15.1 (Keras 2) cannot deserialise. `ml/convert_notebook_model.py` rebuilds `build_balanced_model()` in Keras 2 and copies the weights; the result matches Keras 3's own weight loading to within 2e-7. It loads in about 5 s and predicts in about 150 ms per frame on 4 CPU cores. The notebook's own test results for this model were close to chance (accuracy 0.53–0.62, looking-away recall 0 at thresholds ≤ 0.5), so it rarely flags looking away. Face-count checks do not depend on it.
- **Model:** the notebook's final run trained MobileNetV3Small. The thesis names EfficientNetV2S, so `ml/architectures.py` includes both, and `ml/evaluate.py` produces the comparison table (Table 5.1).
- **Split:** the notebook used 70/15/15; `ml/prepare_data.py` uses 80/15/5 as the build guide specifies.
- **Model selection:** the notebook selected on "looking away" recall. Its last evaluation predicted "looking at" for all 294 images (away recall 0). `ml/train.py` checkpoints on validation AUC, and `ml/evaluate.py` ranks models by macro F1 then AUC.
- **Evidence key:** `{username}/{exam_id}/{timestamp}.jpg`. The exam id was added to the thesis's `{username}/{timestamp}.jpg`.
- **Incidents:** no face, multiple faces and looking away each create a `ProctoringIncident`. Temporal flags are raised for 3+ away incidents in 30 s, 15 s+ continuously away, or any multiple-faces incident. Staff mark each incident reviewed; nothing is penalised automatically.
- **Feedback to students:** answers show "Answer saved" but not whether they are correct, because showing correctness would leak `correct_answer`.

## Open points to confirm against the thesis

- Wording of the Appendix B test IDs (`docs/test-matrix.md` uses inferred descriptions).
- The orientation adjustments relax the threshold towards "looking at" for turned heads, as in the notebook. Check this matches section 4.3.6, since a turned head often means looking away.
