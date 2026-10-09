// The exam page a student sits. Flow: consent screen -> turn on camera + share whole
// screen -> begin exam -> answer questions while a webcam frame is checked every 3 s
// (live preview, green/amber/red status, warning pop-ups) -> finish, which stops
// camera and screen sharing and shows the score.
// If the backend pauses the exam (3 looking-away detections), questions are hidden and the
// ExamPaused pop-up appears; the page polls until staff let the student continue or end it.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import useGazeTracking from "../hooks/useGazeTracking";
import useMediaStream from "../hooks/useMediaStream";
import { api } from "../services/api";
import ConsentNotice from "./ConsentNotice";
import ExamPaused from "./ExamPaused";
import Question from "./Question";

const STATUS = {
  idle: { label: "Starting monitoring…", tone: "grey" },
  at: { label: "Looking at screen", tone: "green" },
  away: { label: "Looking away", tone: "amber" },
  no_face: { label: "No face detected", tone: "red" },
  multiple: { label: "Multiple faces", tone: "red" },
};

function StatusIndicator({ status }) {
  const s = STATUS[status] || STATUS.idle;
  return (
    <div className={`status status-${s.tone}`} data-testid="gaze-status" data-tone={s.tone}>
      <span className="dot" aria-hidden="true" /> {s.label}
    </div>
  );
}

export const PAUSE_POLL_MS = 5000;

function CameraPreview({ stream }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && stream) {
      ref.current.srcObject = stream;
      ref.current.play?.().catch(() => {});
    }
  }, [stream]);
  return <video ref={ref} className="preview" muted playsInline autoPlay data-testid="camera-preview" />;
}

export default function ExamSitting({ id }) {
  const examId = Number(id);
  const [exam, setExam] = useState(null);
  const [consent, setConsent] = useState(null);
  const [phase, setPhase] = useState("loading"); // loading | consent | setup | sitting | paused | done | terminated
  const [attempt, setAttempt] = useState(null);
  const [page, setPage] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const media = useMediaStream();
  const { stopAll } = media;
  const videoRef = useRef(null);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  const ready = Boolean(media.camera && media.screen);
  const monitoring = phase === "sitting" && ready;
  const gaze = useGazeTracking(videoRef, examId, { enabled: monitoring });

  useEffect(() => {
    Promise.all([api.exam(examId), api.consent()])
      .then(([e, c]) => {
        setExam(e);
        setConsent(c);
        setPhase(c.consent_given_at ? "setup" : "consent");
      })
      .catch((e) => setError(e.message));
  }, [examId]);

  // Keep a hidden <video> fed from the camera for frame capture.
  useEffect(() => {
    if (videoRef.current && media.camera) {
      videoRef.current.srcObject = media.camera;
      videoRef.current.play?.().catch(() => {});
    }
  }, [media.camera]);

  // Warning toast for each new flagged frame (FR4).
  useEffect(() => {
    if (!gaze.latest?.warning) return undefined;
    setToast(gaze.latest.warning);
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [gaze.latest]);

  const loadQuestion = useCallback(async (index) => {
    setPage(await api.question(examId, index));
  }, [examId]);

  // Move the page to whatever state the backend says the attempt is in.
  const applyAttempt = useCallback(async (a) => {
    setAttempt(a);
    if (a.status === "paused") {
      setPhase("paused");
    } else if (a.status === "terminated") {
      stopAll();
      setResult(await api.progress(examId));
      setPhase("terminated");
    } else if (a.status === "in_progress") {
      const wasPaused = phaseRef.current === "paused";
      await loadQuestion(page?.index ?? 0);
      setPhase("sitting");
      if (wasPaused) {
        setToast("The supervisor has allowed you to continue.");
        setTimeout(() => setToast(null), 5000);
      }
    }
  }, [examId, loadQuestion, stopAll, page]);

  // The frame that triggered the pause comes back with exam_paused: true.
  useEffect(() => {
    if (gaze.latest?.exam_paused) {
      setAttempt((a) => ({ ...a, status: "paused", help_requested_at: null }));
      setPhase("paused");
    }
  }, [gaze.latest]);

  // While paused, check for the staff decision.
  useEffect(() => {
    if (phase !== "paused") return undefined;
    const id = setInterval(() => {
      api.attempt(examId).then((a) => { if (a.status !== "paused") applyAttempt(a); }).catch(() => {});
    }, PAUSE_POLL_MS);
    return () => clearInterval(id);
  }, [phase, examId, applyAttempt]);

  // A 409 while answering can mean the exam was paused or ended meanwhile.
  const syncAfterConflict = useCallback(async (err) => {
    if (err?.status === 409) {
      try { await applyAttempt(await api.attempt(examId)); return; } catch { /* fall through */ }
    }
    throw err;
  }, [applyAttempt, examId]);

  async function acceptConsent() {
    setBusy(true);
    try {
      setConsent(await api.giveConsent());
      setPhase("setup");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function begin() {
    setBusy(true);
    setError(null);
    try {
      const a = await api.startExam(examId);
      setAttempt(a);
      if (a.status === "paused") {
        setPhase("paused");
      } else {
        await loadQuestion(0);
        setPhase("sitting");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!window.confirm("Submit your exam? You cannot change answers afterwards.")) return;
    setBusy(true);
    try {
      setResult(await api.submitExam(examId));
      media.stopAll();
      setPhase("done");
    } catch (e) {
      try { await syncAfterConflict(e); } catch { setError(e.message); }
    } finally {
      setBusy(false);
    }
  }

  if (error && phase === "loading") return <p role="alert" className="error">{error}</p>;
  if (phase === "loading") return <p>Loading exam…</p>;

  if (phase === "consent") return <ConsentNotice info={consent} onAccept={acceptConsent} busy={busy} />;

  if (phase === "terminated") {
    return (
      <main className="card narrow">
        <h1>Exam ended by the supervisor</h1>
        <p>The exam supervisor reviewed your session and ended this exam.</p>
        {attempt?.decision_note && <p>Supervisor&apos;s note: <em>{attempt.decision_note}</em></p>}
        {result && <p>You answered {result.answered} of {result.total_questions} questions before the exam was paused.</p>}
        <p className="muted">Camera and screen sharing have been stopped. Contact the exam supervisor if you have questions.</p>
        <Link href="/exams">Back to exams</Link>
      </main>
    );
  }

  if (phase === "done") {
    return (
      <main className="card narrow">
        <h1>Exam submitted</h1>
        <p>You answered {result.answered} of {result.total_questions} questions.</p>
        {result.score != null && <p>Score: <strong>{result.score} / {result.max_score}</strong></p>}
        <p className="muted">Camera and screen sharing have been stopped.</p>
        <Link href="/exams">Back to exams</Link>
      </main>
    );
  }

  return (
    <main className="exam-layout">
      <video ref={videoRef} muted playsInline hidden data-testid="capture-video" />
      <aside className="card monitor">
        <h2>{exam.title}</h2>
        {media.camera ? <CameraPreview stream={media.camera} /> : <div className="preview placeholder">Camera off</div>}
        {monitoring && <StatusIndicator status={gaze.status} />}
        <ul className="checks">
          <li className={media.camera ? "ok" : ""}>
            Camera {media.camera ? "on" : <button onClick={media.startCamera}>Enable camera</button>}
          </li>
          <li className={media.screen ? "ok" : ""}>
            Screen sharing {media.screen ? "on" : <button onClick={media.startScreen}>Share screen</button>}
          </li>
        </ul>
        {media.errors.camera && <p role="alert" className="error">{media.errors.camera}</p>}
        {media.errors.screen && <p role="alert" className="error">{media.errors.screen}</p>}
        {gaze.error && <p className="error small">Monitoring: {gaze.error}</p>}
      </aside>

      <section className="card">
        {error && <p role="alert" className="error">{error}</p>}
        {!ready && (
          <p className="notice">
            {phase === "sitting"
              ? "Your camera or screen sharing stopped. Questions are hidden until both are back on."
              : "Turn on your camera and share your entire screen to begin."}
          </p>
        )}
        {phase === "paused" && <p className="notice">Exam paused. Questions are hidden until the supervisor decides.</p>}
        {phase === "setup" && ready && (
          <button onClick={begin} disabled={busy}>Begin exam</button>
        )}
        {phase === "sitting" && ready && page && (
          <>
            <Question page={page} onSubmit={(qid, ans) => api.answer(examId, qid, ans).catch(syncAfterConflict)} />
            <nav className="qnav">
              <button onClick={() => loadQuestion(page.index - 1).catch(syncAfterConflict)} disabled={page.index === 0}>Previous</button>
              <button onClick={() => loadQuestion(page.index + 1).catch(syncAfterConflict)} disabled={page.index + 1 >= page.total}>Next</button>
              <button className="danger" onClick={finish} disabled={busy}>Finish exam</button>
            </nav>
          </>
        )}
      </section>

      {phase === "paused" && <ExamPaused examId={examId} attempt={attempt} />}
      {toast && phase !== "paused" && <div role="alert" className="toast">{toast}</div>}
    </main>
  );
}
