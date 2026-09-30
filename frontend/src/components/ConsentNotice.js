// Shown before a student's first exam (NFR4 / GDPR-minded data handling).
export default function ConsentNotice({ info, onAccept, busy }) {
  const interval = info?.capture_interval_seconds ?? 3;
  const days = info?.retention_days ?? 30;
  return (
    <section className="card consent" aria-labelledby="consent-title">
      <h2 id="consent-title">Before you start: how this exam is monitored</h2>
      <ul>
        <li>Your webcam is used during the exam. <strong>One still image is taken every {interval} seconds</strong>; no continuous video or audio is recorded.</li>
        <li>Each image is checked automatically for whether a face is visible, whether more than one face is present, and whether you appear to be looking at the screen.</li>
        <li>An image is <strong>stored only</strong> when one of those checks raises a flag. Other images are discarded after checking.</li>
        <li>You must share your entire screen for the duration of the exam. Screen contents are not recorded.</li>
        <li>Flags are reviewed by a member of staff. <strong>No penalty is applied automatically.</strong></li>
        <li>Stored images are deleted after <strong>{days} days</strong>. Only authorised staff can view them.</li>
      </ul>
      <button onClick={onAccept} disabled={busy}>I understand and agree</button>
    </section>
  );
}
