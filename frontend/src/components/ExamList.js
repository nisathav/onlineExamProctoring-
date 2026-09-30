import { useEffect, useState } from "react";
import { Link } from "wouter";
import { api } from "../services/api";

export default function ExamList() {
  const [exams, setExams] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.exams().then(setExams).catch((e) => setError(e.message));
  }, []);

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!exams) return <p>Loading exams…</p>;

  return (
    <main className="card">
      <h1>Available exams</h1>
      {exams.length === 0 ? (
        <p>No exams are open right now.</p>
      ) : (
        <ul className="list">
          {exams.map((exam) => (
            <li key={exam.id}>
              <div>
                <strong>{exam.title}</strong>
                <p className="muted">{exam.description}</p>
                <p className="muted">{exam.question_count} questions · {exam.duration_minutes} minutes</p>
              </div>
              <Link href={`/exam/${exam.id}`} className="button">Start</Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
