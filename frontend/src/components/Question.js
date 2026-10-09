// Shows one multiple-choice question and saves the chosen answer. It only confirms
// "Answer saved"; it never reveals whether the answer is correct.
import { useEffect, useState } from "react";

// One question at a time. Feedback confirms the answer was saved; correctness is not revealed.
export default function Question({ page, onSubmit }) {
  const { question, index, total, selected_answer: saved } = page;
  const [choice, setChoice] = useState(saved || "");
  const [feedback, setFeedback] = useState(saved ? "Answer saved" : null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setChoice(saved || "");
    setFeedback(saved ? "Answer saved" : null);
  }, [question.id, saved]);

  async function submit(e) {
    e.preventDefault();
    if (!choice) return;
    setBusy(true);
    try {
      await onSubmit(question.id, choice);
      setFeedback("Answer saved");
    } catch (err) {
      setFeedback(`Could not save answer: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="question">
      <p className="muted">Question {index + 1} of {total} · {question.marks} mark{question.marks === 1 ? "" : "s"}</p>
      <fieldset>
        <legend>{question.text}</legend>
        {question.options.map((opt) => (
          <label key={opt} className="option">
            <input
              type="radio"
              name={`q-${question.id}`}
              value={opt}
              checked={choice === opt}
              onChange={() => { setChoice(opt); setFeedback(null); }}
            />
            {opt}
          </label>
        ))}
      </fieldset>
      <button type="submit" disabled={!choice || busy}>Save answer</button>
      {feedback && <p role="status" className="feedback">{feedback}</p>}
    </form>
  );
}
