# Enhanced Online Proctoring System — Build Guide for Claude Code

This guide turns the thesis design (Chapters 3–4 and Appendix B) into a step-by-step build you can run with Claude Code. Work through the phases in order; each one has a prompt you can paste, and a "done when" checklist to verify before moving on.

Pair it with the `CLAUDE.md` file (delivered alongside this guide), which goes in the root of the repository so Claude Code reads the project rules at the start of every session.

---

## 1. What you're building (from the thesis)

| Area | Decision |
|---|---|
| Front end | React 18.3.1, Wouter routing, custom hooks (`useMediaStream`, `useGazeTracking`) |
| Back end | Python 3.10, FastAPI 0.115.4, SQLAlchemy ORM, Pydantic, Swagger at `/docs` |
| Auth | JWT (python-jose), bcrypt hashing (passlib), OAuth2 password flow, roles: `student`, `staff` |
| Database | PostgreSQL 15 |
| Evidence storage | MinIO (S3-compatible), files named `{username}/{timestamp}.jpg` |
| ML | MediaPipe 0.10.21 face detection + TensorFlow 2.15.1 gaze classifier (EfficientNetV2S transfer learning, asymmetric focal loss, threshold 0.5 with orientation-based adaptive adjustment) |
| Monitoring | Webcam frame captured every **3 seconds** (not continuous video); screen sharing required before the exam starts |
| Deployment | Docker + Docker Compose: `frontend`, `backend`, `db`, `minio`; health checks, resource limits, non-root users |
| Testing | pytest (back end, ≥75% coverage), Jest 29.7 + React Testing Library (front end) |

**Requirements to satisfy (MoSCoW):**

- Must: FR1 authentication, FR2 live webcam, FR3 ML face-away detection + proctor alert, FR6 screen sharing required, NFR2 authenticated API, NFR4 GDPR/FERPA-minded data handling
- Should: NFR1 100 concurrent students, NFR3 high uptime
- Could: FR4 student warnings, NFR5 satisfaction 4/5
- Won't (this iteration, but worth adding — see Phase 7): FR5 consolidated session report

---

## 2. Before you start

1. **Install tools:** Git, Docker Desktop, Node 18+, Python 3.10, and Claude Code.
2. **Create the repo** and drop `CLAUDE.md` in the root.
3. **Plan where training happens.** Training EfficientNetV2S needs a GPU (the thesis used an NVIDIA L4). Have Claude Code write the training scripts, but run them on Colab, Kaggle or a GPU machine, then copy the saved model into `backend/models/`.
4. **Get the datasets.** AFLW2000-3D and CMU Multi-PIE (check each dataset's licence terms; Multi-PIE requires a licence agreement). Label into two classes: `looking_at` and `looking_away`.
5. **Copy `.env.example` → `.env`** once Phase 1 creates it. Never commit `.env`.

### How to work with Claude Code on this project

- **One phase per session** (or `/clear` between phases). Keep the context focused.
- **Plan first.** Start each phase in plan mode, or say "Make a plan first, don't write code yet." Read the plan, correct it, then let it build.
- **Tests alongside code.** Ask for tests in the same phase, and have Claude run them before it says it's done.
- **Commit after each phase** ("commit this with a descriptive message"), so you can roll back.
- **Point it at the thesis.** Save the PDF (or the relevant sections as `docs/thesis-notes.md`) in the repo and reference it: "Follow section 4.2.4 of docs/thesis-notes.md."
- **Screenshots for your thesis figures:** the phases map onto Figures 4.10–4.44, so capture code and UI as you go.

---

## 3. Target folder structure

```
proctoring-system/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── docs/thesis-notes.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                  # migrations
│   ├── models/gaze_model.keras   # trained model (git-ignored or LFS)
│   ├── app/
│   │   ├── main.py               # FastAPI app, middleware, routers
│   │   ├── core/config.py        # settings from env
│   │   ├── core/security.py      # JWT, hashing, role dependencies
│   │   ├── db/session.py         # engine, SessionLocal, get_db
│   │   ├── models/               # SQLAlchemy models
│   │   ├── schemas/              # Pydantic schemas
│   │   ├── api/routes/           # auth, exams, answers, proctoring, progress, reports
│   │   ├── services/storage.py   # MinIO client
│   │   ├── services/face_detector.py   # MediaPipe
│   │   ├── services/gaze_service.py    # model load, preprocess, predict, threshold
│   │   └── ml/losses.py          # asymmetric focal loss (shared with training)
│   └── tests/
├── ml/
│   ├── data/                     # git-ignored
│   ├── prepare_data.py           # labelling, 80/15/5 stratified split
│   ├── architectures.py          # 5 candidate models
│   ├── train.py
│   ├── evaluate.py               # Table 5.1 metrics
│   └── losses.py -> ../backend/app/ml/losses.py
└── frontend/
    ├── Dockerfile
    ├── src/
    │   ├── App.js                # Wouter routes
    │   ├── services/api.js       # fetch wrapper + token handling
    │   ├── hooks/useMediaStream.js
    │   ├── hooks/useGazeTracking.js
    │   ├── components/Login.js
    │   ├── components/ExamList.js
    │   ├── components/ExamSitting.js
    │   ├── components/Question.js
    │   └── components/proctor/   # dashboard, incident review
    └── src/__tests__/
```

---

## 4. Build phases

### Phase 0 — Scaffold and project memory

**Prompt:**
> Read CLAUDE.md. Scaffold the folder structure in BUILD_GUIDE.md section 3 with empty/minimal files, a root .gitignore (Python, Node, .env, ml/data, *.keras), and a README with setup steps. Don't implement features yet.

**Done when:** tree matches section 3; `git status` shows no secrets or data.

---

### Phase 1 — Docker Compose skeleton

**Prompt:**
> Create docker-compose.yml with four services: frontend (React dev server, later nginx), backend (FastAPI on 8000), db (postgres:15 with a named volume), minio (with console, named volume). Put them on one dedicated network. Add health checks for every service (backend exposes GET /health), resource limits, depends_on with condition: service_healthy, and non-root users in the backend and frontend Dockerfiles. All credentials come from .env; create .env.example. Backend should just return {"status":"ok"} for now.

**Done when:** `docker compose up` shows all four healthy; `/health` responds; MinIO console opens.
*Thesis refs:* 4.2.5, Figures 4.10, 4.33–4.38.

---

### Phase 2 — Database models and auth (FR1, NFR2)

**Prompt:**
> Implement the data layer from section 4.2.4: SQLAlchemy models User, Student, Staff, Examination, Question, StudentAnswer with the listed fields and relationships (question options stored as JSON). Add a ProctoringIncident model too (id, student_id, examination_id, timestamp, incident_type, confidence, evidence_key) since FR3/FR5 need somewhere to record incidents. Use Alembic for migrations. Then implement auth: register, login via OAuth2PasswordRequestForm returning a JWT, bcrypt hashing, token expiry, get_current_user and require_role("student"|"staff") dependencies. Every non-auth route must require a valid token. Write pytest tests covering Appendix B cases AUTH-1 to AUTH-7 and SEC-1 to SEC-3.

**Done when:** tests pass; Swagger `/docs` shows auth routes with the lock icon; tampered/expired tokens are rejected.
*Thesis refs:* 4.2.2 (auth), 4.3.1, 4.3.5, Figures 4.13–4.16, 4.40–4.41.

---

### Phase 3 — Examination API

**Prompt:**
> Build the exam endpoints: staff can create/update exams and questions; students can list active exams, start an exam, fetch questions one at a time (never expose correct_answer to students), submit answers (auto-mark is_correct and marks_obtained), and get progress. Use Pydantic schemas for all input/output. Add a seed script with one staff user, one student and a sample 10-question MCQ exam. Tests for EXAM-1 to EXAM-4 and role separation.

**Done when:** you can run a full exam through Swagger as a student; students can't hit staff routes.
*Thesis refs:* 4.2.2 (examination, API components), Figures 4.6–4.7, 4.11–4.12.

---

### Phase 4 — Train the gaze model (outside the app)

Do this in `ml/`. Have Claude Code write the scripts; run training on a GPU.

**Prompt (data):**
> Write ml/prepare_data.py: load labelled images from ml/data/{looking_at,looking_away}, crop faces with MediaPipe, resize to the EfficientNetV2S input size, and create a stratified 80/15/5 train/val/test split saved as file lists. Print class counts per split.

**Prompt (models + training):**
> Write ml/losses.py with an asymmetric focal loss (separate alpha/gamma for the positive "looking_away" class) registered with @tf.keras.utils.register_keras_serializable. Write ml/architectures.py with five candidates: basic CNN, MobileNetV3 transfer, EfficientNetV2S transfer (ImageNet weights, frozen base then fine-tune top layers), custom CNN with attention, and an ensemble of CNNs. Write ml/train.py using data augmentation (brightness/contrast, flips, small rotations, especially for the minority class), class weights, early stopping, and saving the best model as .keras.

**Prompt (evaluation):**
> Write ml/evaluate.py: for each model on the test set, compute accuracy, per-class precision/recall/F1, ROC AUC and mean inference time per sample; run threshold optimisation on the validation set; output a table like Table 5.1 as CSV and markdown, plus a confusion matrix image per model.

**Done when:** you have the comparison table, and the chosen model (EfficientNetV2S in the thesis) is saved to `backend/models/gaze_model.keras`.
*Watch out:* choose the model on F1 + AUC, not "looking away" recall alone. The thesis found weaker models got 100% recall by predicting "away" for everything.
*Thesis refs:* 3.2.5, 3.3.4, 4.2.3, 4.3.2, Figures 4.17, 4.21–4.22, Table 5.1.

---

### Phase 5 — Inference and proctoring endpoint (FR3)

**Prompt:**
> Implement the proctoring pipeline in the backend. services/face_detector.py: MediaPipe face detection returning face count, bounding box and a head-orientation estimate. services/gaze_service.py: load gaze_model.keras once at startup (pass the focal loss as a custom object, import it from app/ml/losses.py), preprocess the cropped face, predict, apply threshold 0.5 adjusted by face orientation (adaptive thresholding, section 4.3.6). Create POST /proctoring/frame that accepts a base64 or multipart JPEG plus exam_id, runs detection in a thread pool so it doesn't block the event loop, and returns {face_detected, face_count, gaze: "at"|"away", confidence, warning}. If the face is missing, more than one face appears, or gaze is away, save the frame to MinIO as {username}/{exam_id}/{timestamp}.jpg and write a ProctoringIncident row. Log end-to-end processing time. Tests: mock the model and cover FACE-1 to FACE-8 logic, INT-2 and INT-4.

**Done when:** posting a sample image returns a sensible result in under 1 second; incidents appear in the DB and MinIO.
*Thesis refs:* 4.2.2 (facial detection, behavioural analysis), Figures 4.18–4.20, 4.42.

---

### Phase 6 — Front end: login, exams, webcam, screen share (FR1, FR2, FR4, FR6)

**Prompt:**
> Build the React front end. App.js with Wouter routes: /login, /exams, /exam/:id, /proctor. Login.js posts form data to the OAuth2 token endpoint and stores the token via services/api.js (attach Authorization header, redirect to /login on 401). hooks/useMediaStream.js: request webcam and screen-share (getDisplayMedia) with clear errors for denied permission, non-HTTPS contexts and unsupported browsers (Safari). hooks/useGazeTracking.js: every 3 seconds grab a frame from the webcam video into a canvas, send it to /proctoring/frame, keep an incident history, and expose the latest status. ExamSitting.js: require screen sharing and camera before showing questions, show a live camera preview with a status indicator (green: looking at screen, amber: looking away, red: no face), show a warning toast on face-away, stop streams when the exam ends. Question.js: render one question, answer selection, submit, show feedback. Jest + RTL tests for components and hooks (mock getUserMedia/getDisplayMedia and fetch).

**Done when:** a student can log in, share screen, sit an exam, see warnings when looking away; streams stop on submit.
*Thesis refs:* 4.3.3, Figures 4.23–4.32.

---

### Phase 7 — Proctor view and session report (FR3 alerts, FR5)

The thesis left the consolidated report as "won't have"; building a simple version closes that gap and strengthens your evaluation.

**Prompt:**
> Add staff-only endpoints: GET /reports/exams/{id} (per-student incident counts, first/last incident, score) and GET /reports/exams/{id}/students/{sid} (timeline of incidents with presigned MinIO URLs to evidence images). Add temporal analysis: flag a student when there are 3+ face-away incidents within 30 seconds, or long away periods. Build /proctor in React: a live-ish list of students in an exam (poll every 5–10 s) with alert badges, and an incident review page showing the timeline and images, with buttons to mark each incident "reviewed – ok" or "needs follow-up" (human in the loop; never auto-penalise).

**Done when:** staff can see who was flagged and review the evidence images.

---

### Phase 8 — Security hardening (NFR2, NFR4)

**Prompt:**
> Harden the app: HTTPS redirect middleware in production, strict CORS allowing only the front-end origin, security headers, rate limiting on login, request size limits on /proctoring/frame, no secrets or tokens in URLs, MinIO bucket private with short-lived presigned URLs, and a data-retention job that deletes evidence older than a configurable number of days. Add a consent screen before the first exam explaining what is captured, how often, and how long it's kept. Tests for SEC-4, API-1 to API-5, DATA-1 to DATA-3.

*Thesis refs:* 4.3.5, 4.3.6, Figures 4.39, 4.43–4.44, Tables B.5–B.7.

---

### Phase 9 — Testing, coverage and load (NFR1)

**Prompt:**
> Run the full backend and frontend test suites with coverage and fix failures. Make sure every Appendix B test ID (AUTH, EXAM, SCRN, FACE, SEC, API, DATA, INT) maps to at least one automated test or a documented manual step in docs/test-matrix.md. Write a Locust script that simulates N students logging in and posting a frame every 3 seconds; run it at 25, 50 and 100 users and record p50/p95 latency and error rate.

**Done when:** backend coverage ≥75%; test matrix complete; load results recorded (these feed Section 5.3.2).

---

### Phase 10 — Production build and deploy

**Prompt:**
> Make the frontend Dockerfile a multi-stage build served by nginx as non-root. Add a docker-compose.prod.yml with a reverse proxy terminating TLS, no exposed DB/MinIO ports, restart policies, and log rotation. Write docs/deploy.md for deploying to a cloud VM.

---

## 5. Manual checks Claude Code can't do for you

- Run the 50-image manual accuracy test (25 at / 25 away) with a real webcam and note per-image inference time.
- Test screen sharing in Chrome, Firefox, Edge and Safari.
- Test in poor lighting and at a 45° angle.
- Collect user feedback (NFR5) if you have time — the thesis lists it as not measured.

## 6. Things to keep consistent with the thesis

- Capture interval: 3 s. Threshold: 0.5 (with orientation adjustment).
- Binary classes: `looking_at` / `looking_away`; "looking down" counts as away.
- Evidence naming by username + timestamp.
- Human review before any integrity decision.
- If you change any of these while building, update the thesis text to match.
