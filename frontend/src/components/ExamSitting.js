// The exam page a student sits. Flow: consent screen -> turn on camera + share whole
// screen -> begin exam -> answer questions while a webcam frame is checked every 3 s
// (live preview, green/amber/red status, warning pop-ups) -> finish, which stops
// camera and screen sharing and shows the score.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import useGazeTracking from "../hooks/useGazeTracking";
import useMediaStream from "../hooks/useMediaStream";
import { api } from "../services/api";
import ConsentNotice from "./ConsentNotice";
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
  const [phase, setPhase] = useState("loading"); // loading | consent | setup | sitting | done
  const [page, setPage] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const media = useMediaStream();
  const videoRef = useRef(null);

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
      await api.startExam(examId);
      await loadQuestion(0);
      setPhase("sitting");
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
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && phase === "loading") return <p role="alert" className="error">{error}</p>;
  if (phase === "loading") return <p>Loading exam…</p>;

  if (phase === "consent") return <ConsentNotice info={consent} onAccept={acceptConsent} busy={busy} />;

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
        {phase === "setup" && ready && (
          <button onClick={begin} disabled={busy}>Begin exam</button>
        )}
        {phase === "sitting" && ready && page && (
          <>
            <Question page={page} onSubmit={(qid, ans) => api.answer(examId, qid, ans)} />
            <nav className="qnav">
              <button onClick={() => loadQuestion(page.index - 1)} disabled={page.index === 0}>Previous</button>
              <button onClick={() => loadQuestion(page.index + 1)} disabled={page.index + 1 >= page.total}>Next</button>
              <button className="danger" onClick={finish} disabled={busy}>Finish exam</button>
            </nav>
          </>
        )}
      </section>

      {toast && <div role="alert" className="toast">{toast}</div>}
    </main>
  );
}
