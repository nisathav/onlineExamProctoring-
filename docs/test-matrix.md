# Test matrix (Appendix B)

Each Appendix B test ID maps to an automated test, or to a manual step where automation isn't possible (real browsers, real webcams). Test names and docstrings carry these IDs.

> The ID descriptions below were inferred from the build guide. Check each one against the thesis's Appendix B tables and adjust the wording if they differ.

## Authentication — AUTH

| ID | What | Automated test |
|---|---|---|
| AUTH-1 | Student registration | `backend/tests/test_auth.py::test_auth_1_register_student` |
| AUTH-2 | Duplicate / invalid registration rejected | `test_auth_2_duplicate_registration_rejected`, `test_auth_2b_weak_input_rejected` |
| AUTH-3 | Login returns JWT (OAuth2 form) | `test_auth_3_login_returns_jwt`; frontend `api.test.js`, `components.test.js` (Login) |
| AUTH-4 | Wrong credentials rejected | `test_auth_4_wrong_password_rejected`; frontend Login error test |
| AUTH-5 | Passwords stored as bcrypt hashes | `test_auth_5_passwords_are_bcrypt_hashed` |
| AUTH-6 | Current user from token | `test_auth_6_me_returns_current_user` |
| AUTH-7 | Role separation (student vs staff) | `test_auth_7_role_separation`, `test_auth_7b_staff_registration_needs_staff_token`; frontend App routing tests |

## Examination — EXAM

| ID | What | Automated test |
|---|---|---|
| EXAM-1 | Students list active exams only | `test_exams.py::test_exam_1_student_lists_only_active_exams`; frontend ExamList |
| EXAM-2 | Staff create/update exams and questions | `test_exam_2_staff_creates_and_updates_exam`, `test_exam_2b_invalid_question_rejected` |
| EXAM-3 | One question at a time, never `correct_answer` | `test_exam_3_questions_never_expose_correct_answer`, `test_exam_3b_must_start_and_consent_first`; frontend Question |
| EXAM-4 | Answers auto-marked; progress and score | `test_exam_4_answers_auto_marked_and_progress`, `test_exam_4b_invalid_answers` |

## Exam pause workflow — EXAM-5..EXAM-9, INT-7

| ID | What | Automated test |
|---|---|---|
| EXAM-5 | 3rd looking-away detection pauses the exam; other incidents don't count; limit configurable | `test_pause.py::test_exam_5_*`; frontend `pause.test.js` EXAM-5/6 |
| EXAM-6 | Paused exam blocks questions, answers, submit and frames; reopening shows the pause | `test_exam_6_*`; frontend EXAM-6 |
| EXAM-7 | Student notifies supervisor; staff dashboard banner and review page show it | `test_exam_7_*`; frontend EXAM-7 and staff banner test |
| EXAM-8 | Staff "Allow to continue" resumes and restarts the count | `test_exam_8_*`; frontend EXAM-8 and decision panel test |
| EXAM-9 | Staff "End exam" terminates; student sees the ended screen; streams stop | `test_exam_9_*`; frontend EXAM-9 |
| INT-7 | Resume/end are staff-only | `test_int_7_decisions_are_staff_only` |

## Screen sharing — SCRN

| ID | What | Automated test / manual step |
|---|---|---|
| SCRN-1 | Camera and full-screen share start | `useMediaStream.test.js` SCRN-1 |
| SCRN-2 | Permission denied gives a clear message and blocks the exam | `useMediaStream.test.js` SCRN-2; `components.test.js` SCRN-2 |
| SCRN-3 | Window/tab share rejected; entire screen required | `useMediaStream.test.js` SCRN-3 |
| SCRN-4 | Unsupported browser / non-HTTPS | `useMediaStream.test.js` SCRN-4 |
| SCRN-5 | Share stopped mid-exam hides questions | `useMediaStream.test.js` SCRN-5; `components.test.js` SCRN-5 |
| SCRN-M | Real browsers: Chrome, Firefox, Edge, Safari | **Manual.** Record results per browser (Safari lacks full `getDisplayMedia` support on some versions) |

## Face and gaze — FACE

| ID | What | Automated test / manual step |
|---|---|---|
| FACE-1 | Frontal face uses the 0.5 threshold | `test_proctoring.py::test_face_1_threshold_unchanged_for_frontal_face` |
| FACE-2 | Tilt adjusts the threshold | `test_face_2_tilt_lowers_threshold` |
| FACE-3 | Turned/smiling adjustments and floors | `test_face_3_turned_and_smiling_adjustments_have_floors` |
| FACE-4 | Orientation from landmarks | `test_face_4_orientation_from_landmarks` |
| FACE-5 | Preprocessing matches training | `test_face_5_preprocess_matches_training_pipeline`, `test_face_5b_crop_with_margin_is_clamped` |
| FACE-6 | Looking at screen: no incident | `test_face_6_looking_at_screen_no_incident` |
| FACE-7 | Looking away: incident + evidence | `test_face_7_looking_away_records_incident`, `test_face_7b_tilted_face_borderline_counts_as_at` |
| FACE-8 | No face / multiple faces / no model | `test_face_8_no_face_and_multiple_faces`, `test_face_8b_model_missing_degrades_gracefully`; frontend status mapping |
| FACE-9 | Real MediaPipe, multi-threaded | `test_ml_integration.py::test_face_9_*` |
| FACE-M1 | 50-image manual accuracy test (25 at / 25 away), per-image inference time | **Manual** (BUILD_GUIDE §5) |
| FACE-M2 | Poor lighting, 45° head angle | **Manual** |

## Security — SEC

| ID | What | Automated test |
|---|---|---|
| SEC-1 | All non-auth routes need a token | `test_auth.py::test_sec_1_routes_require_token`; frontend `api.test.js` |
| SEC-2 | Tampered/forged token rejected | `test_sec_2_tampered_token_rejected` |
| SEC-3 | Expired token / deleted user rejected | `test_sec_3_expired_token_rejected`, `test_sec_3b_token_for_deleted_user_rejected`; frontend 401 redirect |
| SEC-4 | Login rate limiting | `test_sec_4_login_rate_limited` |

## API hardening — API

| ID | What | Automated test |
|---|---|---|
| API-1 | Health and OpenAPI with bearer auth | `test_security.py::test_api_1_health_and_docs` |
| API-2 | Security headers | `test_api_2_security_headers` |
| API-3 | Strict CORS | `test_api_3_cors_only_frontend_origin` |
| API-4 | Frame size limits | `test_api_4_frame_size_limit`, `test_api_4b_decoded_frame_size_limit` |
| API-5 | HTTPS redirect + HSTS, no tokens in URLs | `test_api_5_https_redirect_and_hsts`, `test_api_5b_no_tokens_in_urls` |

## Data protection — DATA

| ID | What | Automated test |
|---|---|---|
| DATA-1 | Consent notice before first exam; recorded | `test_data_1_consent_recorded`, `test_exam_3b_*`; frontend DATA-1 |
| DATA-2 | Evidence only via staff presigned URLs | `test_data_2_students_cannot_see_incidents_or_evidence`, `test_presigned_url_uses_public_endpoint_offline` |
| DATA-3 | Retention deletes old evidence | `test_data_3_retention_purges_old_evidence` |

## Integration — INT

| ID | What | Automated test |
|---|---|---|
| INT-1 | Browser captures a frame every 3 s | `useGazeTracking.test.js` INT-1 |
| INT-2 | JSON/multipart upload, bad payloads, MinIO failure | `test_int_2_*` |
| INT-3 | Warnings shown and kept in history | `useGazeTracking.test.js` INT-3; `components.test.js` FR2/FR4 |
| INT-4 | ML runs in the thread pool, under 1 s | `test_int_4_ml_runs_off_event_loop` |
| INT-5 | Model saved with focal loss loads and predicts | `test_ml_integration.py::test_int_5_*` |

## Load (NFR1) — record results here

Run `loadtest/locustfile.py` (see README) and fill in:

| Users | Requests | p50 (ms) | p95 (ms) | Error rate |
|---|---|---|---|---|
| 25 | | | | |
| 50 | | | | |
| 100 | | | | |

Reference measurement from development (4 vCPU, no GPU): EfficientNetV2S single-frame inference took about 530 ms. A frame without a face takes about 20 ms end to end.
