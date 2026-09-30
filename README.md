# Enhanced Online Proctoring System

A web app that monitors students during online exams. Every 3 seconds the browser sends one webcam frame to the backend. MediaPipe checks for a face, and a TensorFlow gaze classifier decides "looking at" or "looking away". The student gets a warning and staff get an incident to review. Screen sharing is required before an exam starts, and flags are decision support only: nothing is penalised automatically.

Project rules are in `CLAUDE.md` and the phase-by-phase plan is in `BUILD_GUIDE.md`.

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 18.3.1, Wouter, Vite dev server, Jest 29.7 + React Testing Library |
| Backend | Python 3.10, FastAPI 0.115.4, SQLAlchemy 2 + Alembic, Pydantic 2, python-jose JWT, passlib/bcrypt |
| ML | MediaPipe 0.10.21 face detection + face mesh, TensorFlow 2.15.1 gaze classifier, asymmetric focal loss |
| Data | PostgreSQL 15, MinIO (private bucket, presigned URLs) |
| Infra | Docker Compose (`frontend`, `backend`, `db`, `minio`), Caddy TLS proxy in production |

## Quick start (Docker)

```bash
cp .env.example .env          # then change the secrets
# optional: put a trained model at backend/models/gaze_model.keras (see "Gaze model")
docker compose up --build
```

- Frontend: http://localhost:3000
- API + Swagger: http://localhost:8000/docs
- MinIO console: http://localhost:9001

The dev stack runs migrations and seeds `staff1 / staffpass123`, `student1 / studentpass123` and a 10-question sample exam (`SEED_DATA=true`).

A student signs in, accepts the monitoring notice, turns on the camera, shares the **entire screen**, and sits the exam. Staff sign in and land on `/proctor`, which lists students with alert badges and refreshes every 7 s. Staff open a student to review evidence images and mark each incident "Reviewed – OK" or "Needs follow-up".

## Gaze model

The app runs without a model. Face checks (no face / multiple faces) still work, `/health` reports `"model_loaded": false`, and no looking-away incidents are raised.

To enable gaze classification, put a Keras model at `backend/models/gaze_model.keras` (it is git-ignored). The model must:

- take a 224×224×3 RGB face crop with **raw 0–255 pixels** (the network includes its own rescaling);
- output one sigmoid value, **P(looking_at)** (label 1 = looking_at, 0 = looking_away).

This matches the training notebook. There are two ways to get a model:

1. **From the notebook.** Its `.h5` files were saved with Keras 3 (TF 2.17), which TF 2.15.1 cannot read directly. The converter rebuilds the architecture in Keras 2 and copies the weights; outputs match the original to within 2e-7:
   `python ml/convert_notebook_model.py improved_gaze_detection_model.h5 backend/models/gaze_model.keras`
   (`improved_gaze_detection_model.h5` and `gaze_model_balanced.h5` contain identical weights.)
2. **Train with the scripts in `ml/`** (use a GPU):
   ```bash
   pip install -r backend/requirements.txt scikit-learn matplotlib
   # put labelled images in ml/data/looking_at/ and ml/data/looking_away/
   python ml/prepare_data.py              # MediaPipe face crops + stratified 80/15/5 split
   python ml/train.py --model all         # basic_cnn, mobilenetv3, efficientnetv2s, attention_cnn, ensemble
   python ml/evaluate.py                  # ml/output/comparison.{csv,md} + confusion matrices
   cp ml/output/efficientnetv2s.keras backend/models/gaze_model.keras
   ```
   Choose on macro F1 + ROC AUC, not looking-away recall alone.

Inference (`backend/app/services/gaze_service.py`) reproduces the notebook's preprocessing: 20% face margin, CLAHE on the L channel, sharpen, BGR→RGB. It also reproduces the orientation-adaptive threshold: base 0.5, lowered for head tilt over 10°, eye-width asymmetry, and smiling, with floors of 0.2 / 0.15.

## Running tests

```bash
# backend (SQLite + fakes; the ML integration tests run when TF/MediaPipe are installed)
docker compose exec backend pytest --cov=app
# or locally
cd backend && pip install -r requirements-dev.txt && pytest --cov=app

# frontend
cd frontend && npm install && npm test -- --coverage
```

Test IDs follow Appendix B. See `docs/test-matrix.md`.

## Migrations

```bash
docker compose exec backend alembic revision --autogenerate -m "msg"
docker compose exec backend alembic upgrade head
```

## Load test (NFR1)

```bash
pip install locust httpx
python loadtest/create_students.py --count 100
locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 100 -r 10 -t 3m --csv loadtest/results/u100
```

## Production

See `docs/deploy.md` (`docker-compose.prod.yml`: nginx non-root frontend, Caddy TLS, no public DB/MinIO ports, log rotation).

## Layout

```
backend/app/        FastAPI app (core, db, models, schemas, api/routes, services, ml/losses.py)
backend/alembic/    migrations
backend/tests/      pytest suite
ml/                 data prep, 5 architectures, training, evaluation (losses.py -> backend)
frontend/src/       React app (App.js, services/api.js, hooks/, components/, __tests__/)
loadtest/           Locust scripts
deploy/Caddyfile    TLS reverse proxy for production
docs/               test matrix, deployment, thesis notes
```
