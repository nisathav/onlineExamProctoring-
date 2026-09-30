# Enhanced Online Proctoring System

Web app that monitors students during online exams: webcam frame every 3 s → MediaPipe face detection → TensorFlow gaze classifier (looking_at / looking_away) → warning to student + incident for proctor review. Screen sharing is required before an exam starts. Full build plan: BUILD_GUIDE.md.

## Stack (keep these versions)
- Backend: Python 3.10, FastAPI 0.115.4, SQLAlchemy + Alembic, Pydantic, python-jose (JWT), passlib[bcrypt]
- ML: TensorFlow 2.15.1, MediaPipe 0.10.21, OpenCV; model at backend/models/gaze_model.keras (EfficientNetV2S transfer learning, asymmetric focal loss in app/ml/losses.py)
- DB: PostgreSQL 15. Evidence images: MinIO bucket, key `{username}/{exam_id}/{timestamp}.jpg`
- Frontend: React 18.3.1, Wouter for routing, custom hooks useMediaStream and useGazeTracking
- Infra: Docker Compose services frontend, backend, db, minio

## Commands
- Start everything: `docker compose up --build`
- Backend tests: `docker compose exec backend pytest --cov=app`
- Frontend tests: `cd frontend && npm test -- --coverage`
- Migrations: `docker compose exec backend alembic revision --autogenerate -m "msg"` then `alembic upgrade head`
- API docs: http://localhost:8000/docs

## Rules
- Every API route except /health, /auth/register and /auth/token requires a JWT; staff-only routes use require_role("staff").
- Never return Question.correct_answer to students.
- Secrets only from environment variables; never commit .env, datasets or model files.
- Heavy ML work (face detection, prediction) runs in a thread pool, never directly in async route handlers.
- The focal loss must be imported from app/ml/losses.py when loading the model (custom object).
- Capture interval 3 s, gaze threshold 0.5 with orientation-based adjustment. Don't change these without being asked.
- Flags are decision support only: no automatic penalties; staff review incidents.
- Write or update tests with every change and run them before saying a task is done. Map tests to Appendix B IDs (AUTH-x, EXAM-x, FACE-x, SEC-x, API-x, DATA-x, INT-x) in test names or docstrings.
- Plan before large changes; keep changes scoped to the current phase in BUILD_GUIDE.md.
