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

export default function IncidentReview({ examId, studentId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    api.studentTimeline(examId, studentId).then(setData).catch((e) => setError(e.message));
  }, [examId, studentId]);

  useEffect(load, [load]);

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
