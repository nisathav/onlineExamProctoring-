// Staff dashboard: pick an exam and see every student with incident counts, score and
// alert badges. Refreshes automatically every 7 seconds. Students whose exam was auto-paused
// appear in a red banner at the top (with any "notify supervisor" message) until staff decide.
import { useCallback, useEffect, useState } from "react";
import { Link } from "wouter";
import { api } from "../../services/api";

export const POLL_MS = 7000;

function fmt(ts) {
  return ts ? new Date(ts).toLocaleTimeString() : "—";
}

function sortPausedFirst(students) {
  return [...students].sort((a, b) => (b.attempt_status === "paused") - (a.attempt_status === "paused"));
}

function PausedBanner({ report }) {
  const paused = report.students.filter((s) => s.attempt_status === "paused");
  if (paused.length === 0) return null;
  return (
    <div className="alert-banner" role="alert">
      <strong>
        {paused.length} student{paused.length === 1 ? "'s exam is" : "s' exams are"} paused and waiting for your decision
      </strong>
      <ul>
        {paused.map((s) => (
          <li key={s.student_id}>
            {s.full_name || s.username} – {s.pause_reason || "paused"}
            {s.paused_at && ` at ${fmt(s.paused_at)}`}.
            {s.help_requested_at && (
              <> <strong>Asked for help at {fmt(s.help_requested_at)}</strong>
                {s.help_message && <>: &ldquo;{s.help_message}&rdquo;</>}.</>
            )}{" "}
            <Link href={`/proctor/exams/${report.examination_id}/students/${s.student_id}`}>Review now</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ProctorDashboard() {
  const [exams, setExams] = useState([]);
  const [examId, setExamId] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.exams()
      .then((list) => {
        setExams(list);
        const firstActive = list.find((e) => e.is_active) || list[0];
        if (firstActive) setExamId(firstActive.id);
      })
      .catch((e) => setError(e.message));
  }, []);

  const refresh = useCallback(() => {
    if (!examId) return;
    api.examReport(examId).then((r) => { setReport(r); setError(null); }).catch((e) => setError(e.message));
  }, [examId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <main className="card">
      <h1>Proctor dashboard</h1>
      <p className="muted">Flags are decision support only. Review the evidence before taking any action.</p>
      <label>
        Exam{" "}
        <select value={examId ?? ""} onChange={(e) => setExamId(Number(e.target.value))}>
          {exams.map((e) => (
            <option key={e.id} value={e.id}>{e.title}{e.is_active ? "" : " (inactive)"}</option>
          ))}
        </select>
      </label>
      {error && <p role="alert" className="error">{error}</p>}
      {report && <PausedBanner report={report} />}
      {report && (
        report.students.length === 0 ? <p>No students have started this exam yet.</p> : (
          <table className="table">
            <thead>
              <tr>
                <th>Student</th><th>Status</th><th>Incidents</th><th>First / last</th><th>Score</th><th>Alerts</th><th />
              </tr>
            </thead>
            <tbody>
              {sortPausedFirst(report.students).map((s) => (
                <tr key={s.student_id} className={s.attempt_status === "paused" ? "paused" : s.flagged ? "flagged" : ""}>
                  <td>{s.full_name || s.username}<div className="muted small">{s.username}</div></td>
                  <td>{s.attempt_status?.replace("_", " ") ?? "—"}</td>
                  <td>
                    {s.incident_count}
                    <div className="muted small">
                      {Object.entries(s.incidents_by_type).map(([k, v]) => `${k.replace("_", " ")}: ${v}`).join(", ")}
                    </div>
                  </td>
                  <td className="small">{fmt(s.first_incident)} / {fmt(s.last_incident)}</td>
                  <td>{s.score} / {s.max_score}</td>
                  <td>
                    {s.attempt_status === "paused" && <span className="badge red">Paused – decision needed</span>}
                    {s.help_requested_at && <span className="badge amber">Asked for help</span>}
                    {s.attempt_status === "terminated" && <span className="badge">Ended by supervisor</span>}
                    {s.flagged && <span className="badge red" title={s.flag_reasons.join("\n")}>Flagged</span>}
                    {s.pending_reviews > 0 && <span className="badge amber">{s.pending_reviews} to review</span>}
                    {s.flag_reasons.map((r) => <div key={r} className="small">{r}</div>)}
                  </td>
                  <td><Link href={`/proctor/exams/${report.examination_id}/students/${s.student_id}`}>Review</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </main>
  );
}
