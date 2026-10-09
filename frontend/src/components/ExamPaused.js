// Pop-up shown when the exam is paused after repeated looking-away. Tells the student to
// contact the exam supervisor and has a "Notify supervisor" button (with an optional
// message) that pings staff. The exam page keeps checking for the staff decision.
import { useState } from "react";
import { api } from "../services/api";

export default function ExamPaused({ examId, attempt }) {
  const [message, setMessage] = useState("");
  const [notifiedAt, setNotifiedAt] = useState(attempt?.help_requested_at || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function notify() {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.requestHelp(examId, message);
      setNotifiedAt(updated.help_requested_at);
      setMessage("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal" role="alertdialog" aria-labelledby="pause-title" aria-describedby="pause-desc">
        <h2 id="pause-title">Exam paused</h2>
        <p id="pause-desc" className="pause-message">
          Your exam has been paused because you were detected looking away from the screen several
          times. <strong>Please contact the exam supervisor.</strong>
        </p>
        <p className="muted">
          A supervisor will review the situation and decide whether you can continue. Your answers so
          far are saved. Keep this page open and your camera on.
        </p>
        <label>
          Message to the supervisor (optional)
          <textarea
            value={message}
            maxLength={500}
            rows={3}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="e.g. I was reading the question on a second monitor"
          />
        </label>
        <button onClick={notify} disabled={busy}>
          {notifiedAt ? "Notify supervisor again" : "Notify supervisor"}
        </button>
        {notifiedAt && (
          <p role="status" className="feedback">
            Supervisor notified at {new Date(notifiedAt).toLocaleTimeString()}. Please wait for their decision.
          </p>
        )}
        {error && <p role="alert" className="error">{error}</p>}
      </div>
    </div>
  );
}
