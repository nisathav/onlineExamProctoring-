// Tests for the auto-pause workflow: the student's paused pop-up and "Notify supervisor"
// button, resuming or ending after the staff decision, and the staff banner and decision
// panel (EXAM-5..EXAM-9 test IDs).
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import ExamSitting, { PAUSE_POLL_MS } from "../components/ExamSitting";
import IncidentReview from "../components/proctor/IncidentReview";
import ProctorDashboard from "../components/proctor/ProctorDashboard";
import { installMediaDevices, loginAs, mockFetch } from "./testUtils";

function withRouter(ui) {
  const location = memoryLocation({ path: "/", record: true });
  return render(<Router hook={location.hook}>{ui}</Router>);
}

const EXAM = { id: 1, title: "Sample Quiz", description: "d", duration_minutes: 20, is_active: true, question_count: 2 };
const page = (index) => ({
  index, total: 2, selected_answer: null,
  question: { id: 10 + index, order: index + 1, text: `Question text ${index}`, options: ["A", "B"], marks: 1 },
});
const ATTEMPT = { id: 1, examination_id: 1, started_at: "x", status: "in_progress" };
const PAUSED_FRAME = {
  face_detected: true, face_count: 1, gaze: "away", confidence: 0.9,
  warning: "You appear to be looking away from the screen.", exam_paused: true,
  pause_message: "Your exam has been paused. Please contact the exam supervisor.",
};

describe("Student side of the pause (EXAM-5..EXAM-9)", () => {
  let attemptState;
  let calls;

  beforeEach(() => {
    jest.useFakeTimers({ advanceTimers: true });
    loginAs("student");
    HTMLCanvasElement.prototype.getContext = () => ({ drawImage: jest.fn() });
    HTMLCanvasElement.prototype.toDataURL = () => "data:image/jpeg;base64,AAA";
    Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { get: () => 640, configurable: true });
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { get: () => 480, configurable: true });
    attemptState = { ...ATTEMPT, status: "paused" };
    calls = mockFetch({
      "GET /exams/1": EXAM,
      "GET /auth/consent": { consent_given_at: "2025-01-01T00:00:00Z", capture_interval_seconds: 3, retention_days: 30 },
      "POST /exams/1/start": ATTEMPT,
      "GET /exams/1/questions/0": page(0),
      "GET /exams/1/attempt": () => attemptState,
      "POST /exams/1/help": (body) => ({ ...attemptState, help_requested_at: "2025-01-01T10:00:00Z", _msg: body.message }),
      "GET /exams/1/progress": { examination_id: 1, total_questions: 2, answered: 1, status: "terminated", score: 1, max_score: 2 },
      "POST /proctoring/frame": PAUSED_FRAME,
    });
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
  });

  // waitFor/findBy advance the fake clock while they wait, so a generous timeout covers
  // the 3 s capture interval even if the interval was registered a moment late.
  const PAUSE_WAIT = { timeout: 8000 };

  async function startAndGetPaused() {
    const media = installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await userEvent.click(await screen.findByRole("button", { name: /enable camera/i }));
    await userEvent.click(screen.getByRole("button", { name: /share screen/i }));
    await userEvent.click(await screen.findByRole("button", { name: /begin exam/i }));
    expect(await screen.findByText("Question text 0")).toBeInTheDocument();
    await screen.findByRole("alertdialog", {}, PAUSE_WAIT);
    return media;
  }

  test("EXAM-5/6: pause pop-up appears, questions hide and frame capture stops", async () => {
    await startAndGetPaused();
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(/Please contact the exam supervisor/);
    expect(screen.queryByText("Question text 0")).not.toBeInTheDocument();
    const framesBefore = calls.filter((c) => c.key === "POST /proctoring/frame").length;
    await act(async () => { jest.advanceTimersByTime(9000); });
    expect(calls.filter((c) => c.key === "POST /proctoring/frame").length).toBe(framesBefore);
  });

  test("EXAM-7: 'Notify supervisor' pings staff with the optional message", async () => {
    await startAndGetPaused();
    await userEvent.type(screen.getByLabelText(/Message to the supervisor/), "Second monitor");
    await userEvent.click(screen.getByRole("button", { name: "Notify supervisor" }));
    expect(await screen.findByText(/Supervisor notified at/)).toBeInTheDocument();
    const help = calls.find((c) => c.key === "POST /exams/1/help");
    expect(JSON.parse(help.opts.body)).toEqual({ message: "Second monitor" });
    expect(screen.getByRole("button", { name: "Notify supervisor again" })).toBeInTheDocument();
  });

  test("EXAM-8: staff allow to continue -> questions come back with a notice", async () => {
    await startAndGetPaused();
    attemptState = { ...ATTEMPT, status: "in_progress" };
    calls.length = 0;
    global.fetch.mockClear();
    expect(await screen.findByText("Question text 0", {}, { timeout: PAUSE_POLL_MS * 2 })).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText(/allowed you to continue/)).toBeInTheDocument();
  });

  test("EXAM-9: staff end the exam -> ended screen and streams stopped", async () => {
    const { cam, scr } = await startAndGetPaused();
    attemptState = { ...ATTEMPT, status: "terminated", decision_note: "Phone visible" };
    expect(await screen.findByText(/Exam ended by the supervisor/, {}, { timeout: PAUSE_POLL_MS * 2 })).toBeInTheDocument();
    expect(screen.getByText(/Phone visible/)).toBeInTheDocument();
    expect(screen.getByText(/answered 1 of 2/)).toBeInTheDocument();
    expect(cam.track.stop).toHaveBeenCalled();
    expect(scr.track.stop).toHaveBeenCalled();
  });

  test("EXAM-6: reopening a paused exam shows the pause pop-up straight away", async () => {
    calls = mockFetch({
      "GET /exams/1": EXAM,
      "GET /auth/consent": { consent_given_at: "2025-01-01T00:00:00Z", capture_interval_seconds: 3, retention_days: 30 },
      "POST /exams/1/start": { ...ATTEMPT, status: "paused", help_requested_at: "2025-01-01T10:00:00Z" },
      "GET /exams/1/attempt": () => attemptState,
    });
    installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await userEvent.click(await screen.findByRole("button", { name: /enable camera/i }));
    await userEvent.click(screen.getByRole("button", { name: /share screen/i }));
    await userEvent.click(await screen.findByRole("button", { name: /begin exam/i }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText(/Supervisor notified at/)).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("GET /exams/1/questions"))).toBe(false);
  });
});

describe("Staff side of the pause (EXAM-7..EXAM-9)", () => {
  const pausedRow = {
    student_id: 5, username: "student1", full_name: "Sam", attempt_status: "paused",
    incident_count: 3, incidents_by_type: { looking_away: 3 }, first_incident: "2025-01-01T10:00:00Z",
    last_incident: "2025-01-01T10:00:06Z", score: 1, max_score: 10, flagged: true,
    flag_reasons: ["3+ looking-away incidents within 30s"], pending_reviews: 3,
    paused_at: "2025-01-01T10:00:06Z", pause_reason: "Looking away detected 3 times",
    help_requested_at: "2025-01-01T10:01:00Z", help_message: "I dropped my pen",
  };

  test("dashboard shows a red banner for paused students with their help message", async () => {
    loginAs("staff");
    mockFetch({ "GET /exams": [EXAM], "GET /reports/exams/1": { examination_id: 1, title: "Sample Quiz", students: [pausedRow] } });
    withRouter(<ProctorDashboard />);
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(/paused and waiting for your decision/);
    expect(banner).toHaveTextContent(/I dropped my pen/);
    expect(screen.getByRole("link", { name: "Review now" })).toHaveAttribute("href", "/proctor/exams/1/students/5");
    expect(screen.getByText("Paused – decision needed")).toBeInTheDocument();
    expect(screen.getByText("Asked for help")).toBeInTheDocument();
  });

  function timeline(status, extra = {}) {
    return {
      examination_id: 1, student_id: 5, username: "student1", flagged: true, flag_reasons: [],
      attempt_status: status, paused_at: "2025-01-01T10:00:06Z", pause_reason: "Looking away detected 3 times",
      help_requested_at: "2025-01-01T10:01:00Z", help_message: "I dropped my pen", decision_note: "",
      decided_at: null, incidents: [], ...extra,
    };
  }

  test("review page: 'Allow to continue' sends the decision with a note", async () => {
    loginAs("staff");
    let status = "paused";
    const calls = mockFetch({
      "GET /reports/exams/1/students/5": () => timeline(status, status === "in_progress" ? { decided_at: "2025-01-01T10:02:00Z" } : {}),
      "POST /reports/exams/1/students/5/resume": (body) => { status = "in_progress"; return { attempt_status: "in_progress", ...body }; },
    });
    withRouter(<IncidentReview examId="1" studentId="5" />);
    expect(await screen.findByText(/your decision is needed/)).toBeInTheDocument();
    expect(screen.getByText(/I dropped my pen/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Note/), "OK, carry on");
    await userEvent.click(screen.getByRole("button", { name: "Allow to continue" }));
    expect(await screen.findByText(/Allowed to continue at/)).toBeInTheDocument();
    const call = calls.find((c) => c.key === "POST /reports/exams/1/students/5/resume");
    expect(JSON.parse(call.opts.body)).toEqual({ note: "OK, carry on" });
  });

  test("review page: 'End exam' asks for confirmation, then ends it", async () => {
    loginAs("staff");
    window.confirm = jest.fn(() => true);
    let status = "paused";
    mockFetch({
      "GET /reports/exams/1/students/5": () => timeline(status, { decision_note: status === "terminated" ? "Phone visible" : "" }),
      "POST /reports/exams/1/students/5/terminate": () => { status = "terminated"; return { attempt_status: "terminated" }; },
    });
    withRouter(<IncidentReview examId="1" studentId="5" />);
    await userEvent.click(await screen.findByRole("button", { name: "End exam" }));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText(/Exam ended by supervisor: Phone visible/)).toBeInTheDocument());
  });

  test("review page: decision errors are shown", async () => {
    loginAs("staff");
    mockFetch({
      "GET /reports/exams/1/students/5": () => timeline("paused"),
      "POST /reports/exams/1/students/5/resume": [409, { detail: "Only a paused exam can be continued or ended" }],
    });
    withRouter(<IncidentReview examId="1" studentId="5" />);
    await userEvent.click(await screen.findByRole("button", { name: "Allow to continue" }));
    expect(await screen.findByText(/Only a paused exam/)).toBeInTheDocument();
  });
});
