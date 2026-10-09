// Staff page for one student: timeline of incidents with the evidence photos, and buttons
// to mark each one "Reviewed - OK" or "Needs follow-up". Nothing here applies a penalty.
// If the student's exam is paused, a decision panel lets staff allow them to continue or
// end the exam after looking at the captured images.
import { useCallback, useEffect, useState } from "react";
import { Link } from "wouter";
import { api } from "../../services/api";

const TYPE_LABEL = {
  looking_away: "Looking away",
  no_face: "No face",
  multiple_faces: "Multiple faces",
};
const REVIEW_LABEL = {
  pending: "Pending review",
  reviewed_ok: "Reviewed – OK",
  needs_follow_up: "Needs follow-up",
};

function fmtTime(ts) {
  return ts ? new Date(ts).toLocaleTimeString() : "";
}

function AttemptDecisionPanel({ data, examId, studentId, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (data.attempt_status === "terminated") {
    return <p className="badge">Exam ended by supervisor{data.decision_note && `: ${data.decision_note}`}</p>;
  }
  if (data.attempt_status !== "paused") {
    return data.decided_at ? (
      <p className="muted">Allowed to continue at {fmtTime(data.decided_at)}{data.decision_note && ` (${data.decision_note})`}.</p>
    ) : null;
  }

  async function decide(action) {
    if (action === "terminate" && !window.confirm(`End the exam for ${data.username}? They will not be able to continue.`)) return;
    setBusy(true);
    setError(null);
    try {
      await (action === "resume" ? api.resumeAttempt : api.terminateAttempt)(examId, studentId, note);
      setNote("");
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="decision" aria-label="Paused exam decision">
      <h2>Exam paused – your decision is needed</h2>
      <p>{data.pause_reason || "Paused"}{data.paused_at && ` at ${fmtTime(data.paused_at)}`}. Look at the captured images below, then decide.</p>
      {data.help_requested_at && (
        <p className="help-ping">
          <strong>Student asked for help at {fmtTime(data.help_requested_at)}</strong>
          {data.help_message && <>: &ldquo;{data.help_message}&rdquo;</>}
        </p>
      )}
      <label>
        Note (optional, shown to the student)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={1000} />
      </label>
      <div className="actions">
        <button onClick={() => decide("resume")} disabled={busy}>Allow to continue</button>
        <button className="danger" onClick={() => decide("terminate")} disabled={busy}>End exam</button>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
    </section>
  );
}

export default function IncidentReview({ examId, studentId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.studentTimeline(examId, studentId).then(setData).catch((e) => setError(e.message));
  }, [examId, studentId]);

  useEffect(load, [load]);

  // While the exam is paused, refresh so new help requests show up without reloading.
  const paused = data?.attempt_status === "paused";
  useEffect(() => {
    if (!paused) return undefined;
    const id = setInterval(load, 7000);
    return () => clearInterval(id);
  }, [paused, load]);

  async function review(incidentId, status) {
    try {
      const updated = await api.reviewIncident(incidentId, status);
      setData((d) => ({
        ...d,
        incidents: d.incidents.map((i) => (i.id === incidentId ? { ...i, review_status: updated.review_status } : i)),
      }));
    } catch (e) {
      setError(e.message);
    }
  }

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!data) return <p>Loading incidents…</p>;

  return (
    <main className="card">
      <Link href="/proctor">← Back to dashboard</Link>
      <h1>Incidents for {data.username}</h1>
      <AttemptDecisionPanel data={data} examId={examId} studentId={studentId} onDone={load} />
      {data.flagged ? (
        <p className="badge red">Flagged: {data.flag_reasons.join("; ")}</p>
      ) : (
        <p className="muted">Not flagged by temporal analysis.</p>
      )}
      <p className="muted">Mark each incident after looking at the evidence. Nothing here applies a penalty.</p>
      {data.incidents.length === 0 && <p>No incidents recorded.</p>}
      <ol className="timeline">
        {data.incidents.map((inc) => (
          <li key={inc.id} className={`incident ${inc.review_status}`}>
            <div className="incident-head">
              <strong>{TYPE_LABEL[inc.incident_type] || inc.incident_type}</strong>
              <span className="muted">{new Date(inc.timestamp).toLocaleTimeString()}</span>
              <span className="muted">confidence {(inc.confidence * 100).toFixed(0)}%</span>
              <span className="badge">{REVIEW_LABEL[inc.review_status]}</span>
            </div>
            {inc.evidence_url ? (
              <img src={inc.evidence_url} alt={`Evidence for incident ${inc.id}`} className="evidence" />
            ) : (
              <p className="muted small">No image (deleted after retention period or not stored).</p>
            )}
            <div className="actions">
              <button onClick={() => review(inc.id, "reviewed_ok")}>Reviewed – OK</button>
              <button className="danger" onClick={() => review(inc.id, "needs_follow_up")}>Needs follow-up</button>
            </div>
          </li>
        ))}
      </ol>
    </main>
  );
}
