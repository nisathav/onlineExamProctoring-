import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import App from "../App";
import ExamList from "../components/ExamList";
import ExamSitting from "../components/ExamSitting";
import Login from "../components/Login";
import Question from "../components/Question";
import IncidentReview from "../components/proctor/IncidentReview";
import ProctorDashboard from "../components/proctor/ProctorDashboard";
import { installMediaDevices, loginAs, mockFetch, namedError } from "./testUtils";

function withRouter(ui, path = "/") {
  const location = memoryLocation({ path, record: true });
  const utils = render(<Router hook={location.hook}>{ui}</Router>);
  return { ...utils, location };
}

const EXAM = { id: 1, title: "Sample Quiz", description: "d", duration_minutes: 20, is_active: true, question_count: 2 };
const page = (index, extra = {}) => ({
  index,
  total: 2,
  selected_answer: null,
  question: { id: 10 + index, order: index + 1, text: `Question text ${index}`, options: ["A", "B"], marks: 1 },
  ...extra,
});

describe("Login (AUTH)", () => {
  test("AUTH-3: successful student login navigates to /exams", async () => {
    mockFetch({ "POST /auth/token": { access_token: "t", role: "student", username: "student1" } });
    const { location } = withRouter(<Login />, "/login");
    await userEvent.type(screen.getByLabelText(/username/i), "student1");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(location.history.at(-1)).toBe("/exams"));
  });

  test("AUTH-4: failed login shows the error", async () => {
    mockFetch({ "POST /auth/token": [401, { detail: "Incorrect username or password" }] });
    withRouter(<Login />, "/login");
    await userEvent.type(screen.getByLabelText(/username/i), "x");
    await userEvent.type(screen.getByLabelText(/password/i), "y");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect username or password");
  });

  test("staff login goes to /proctor", async () => {
    mockFetch({ "POST /auth/token": { access_token: "t", role: "staff", username: "staff1" } });
    const { location } = withRouter(<Login />, "/login");
    await userEvent.type(screen.getByLabelText(/username/i), "staff1");
    await userEvent.type(screen.getByLabelText(/password/i), "pw");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(location.history.at(-1)).toBe("/proctor"));
  });
});

describe("ExamList (EXAM-1)", () => {
  test("lists active exams with a start link", async () => {
    loginAs("student");
    mockFetch({ "GET /exams": [EXAM] });
    withRouter(<ExamList />, "/exams");
    expect(await screen.findByText("Sample Quiz")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start" })).toHaveAttribute("href", "/exam/1");
  });

  test("empty and error states", async () => {
    mockFetch({ "GET /exams": [] });
    const { unmount } = withRouter(<ExamList />);
    expect(await screen.findByText(/No exams are open/)).toBeInTheDocument();
    unmount();
    mockFetch({ "GET /exams": [500, { detail: "down" }] });
    withRouter(<ExamList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("down");
  });
});

describe("Question (EXAM-3, EXAM-4)", () => {
  test("select and save an answer; correctness is not revealed", async () => {
    const onSubmit = jest.fn().mockResolvedValue({});
    render(<Question page={page(0)} onSubmit={onSubmit} />);
    const save = screen.getByRole("button", { name: /save answer/i });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByLabelText("B"));
    await userEvent.click(save);
    expect(onSubmit).toHaveBeenCalledWith(10, "B");
    expect(await screen.findByRole("status")).toHaveTextContent("Answer saved");
    expect(screen.queryByText(/correct/i)).not.toBeInTheDocument();
  });

  test("shows a previously saved answer and save errors", async () => {
    const onSubmit = jest.fn().mockRejectedValue(new Error("network"));
    render(<Question page={page(1, { selected_answer: "A" })} onSubmit={onSubmit} />);
    expect(screen.getByLabelText("A")).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: /save answer/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("Could not save answer: network");
  });
});

describe("ExamSitting (FR2, FR4, FR6, SCRN, DATA-1)", () => {
  beforeEach(() => {
    jest.useFakeTimers({ advanceTimers: true });
    loginAs("student");
    HTMLCanvasElement.prototype.getContext = () => ({ drawImage: jest.fn() });
    HTMLCanvasElement.prototype.toDataURL = () => "data:image/jpeg;base64,AAA";
    Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { get: () => 640, configurable: true });
    Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { get: () => 480, configurable: true });
    window.confirm = jest.fn(() => true);
  });
  afterEach(() => jest.useRealTimers());

  function routes(overrides = {}) {
    return mockFetch({
      "GET /exams/1": EXAM,
      "GET /auth/consent": { consent_given_at: "2025-01-01T00:00:00Z", capture_interval_seconds: 3, retention_days: 30 },
      "POST /auth/consent": { consent_given_at: "2025-01-01T00:00:00Z", capture_interval_seconds: 3, retention_days: 30 },
      "POST /exams/1/start": { id: 1, examination_id: 1, status: "in_progress", started_at: "x" },
      "GET /exams/1/questions/0": page(0),
      "GET /exams/1/questions/1": page(1),
      "POST /exams/1/answers": { question_id: 10, answer: "A", saved: true },
      "POST /exams/1/submit": { examination_id: 1, total_questions: 2, answered: 2, status: "submitted", score: 1, max_score: 2 },
      "POST /proctoring/frame": { face_detected: true, face_count: 1, gaze: "away", confidence: 0.9, warning: "You appear to be looking away from the screen." },
      ...overrides,
    });
  }

  async function enableMediaAndBegin() {
    await userEvent.click(await screen.findByRole("button", { name: /enable camera/i }));
    await userEvent.click(screen.getByRole("button", { name: /share screen/i }));
    await userEvent.click(await screen.findByRole("button", { name: /begin exam/i }));
  }

  test("DATA-1: consent screen shown first, explaining capture interval and retention", async () => {
    routes({ "GET /auth/consent": { consent_given_at: null, capture_interval_seconds: 3, retention_days: 30 } });
    installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    expect(await screen.findByText(/every 3 seconds/)).toBeInTheDocument();
    expect(screen.getByText(/30 days/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /agree/i }));
    expect(await screen.findByRole("button", { name: /enable camera/i })).toBeInTheDocument();
  });

  test("FR6: questions stay hidden until camera and screen share are both on", async () => {
    routes();
    installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await userEvent.click(await screen.findByRole("button", { name: /enable camera/i }));
    expect(screen.queryByRole("button", { name: /begin exam/i })).not.toBeInTheDocument();
    expect(screen.getByText(/share your entire screen to begin/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /share screen/i }));
    expect(await screen.findByRole("button", { name: /begin exam/i })).toBeInTheDocument();
  });

  test("SCRN-2: denied screen share shows the error and blocks the exam", async () => {
    routes();
    installMediaDevices({ screen: namedError("NotAllowedError") });
    withRouter(<ExamSitting id="1" />);
    await userEvent.click(await screen.findByRole("button", { name: /enable camera/i }));
    await userEvent.click(screen.getByRole("button", { name: /share screen/i }));
    expect(await screen.findByText(/Permission for screen sharing was denied/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /begin exam/i })).not.toBeInTheDocument();
  });

  test("FR2/FR4: live preview, amber status and warning toast when looking away; streams stop on submit", async () => {
    const calls = routes();
    const { cam, scr } = installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await enableMediaAndBegin();
    expect(await screen.findByText("Question text 0")).toBeInTheDocument();
    expect(screen.getByTestId("camera-preview")).toBeInTheDocument();

    await act(async () => { jest.advanceTimersByTime(3000); });
    expect(calls.some((c) => c.key === "POST /proctoring/frame")).toBe(true);
    await waitFor(() => expect(screen.getByTestId("gaze-status")).toHaveAttribute("data-tone", "amber"));
    expect(screen.getByRole("alert")).toHaveTextContent(/looking away/);

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Question text 1")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("A"));
    await userEvent.click(screen.getByRole("button", { name: /save answer/i }));

    await userEvent.click(screen.getByRole("button", { name: /finish exam/i }));
    expect(await screen.findByText(/Exam submitted/)).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(cam.track.stop).toHaveBeenCalled();
    expect(scr.track.stop).toHaveBeenCalled();
  });

  test("SCRN-5: questions are hidden if screen sharing stops mid-exam", async () => {
    routes({ "POST /proctoring/frame": { face_detected: true, face_count: 1, gaze: "at", warning: null } });
    const { scr } = installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await enableMediaAndBegin();
    expect(await screen.findByText("Question text 0")).toBeInTheDocument();
    act(() => scr.track.fire("ended"));
    expect(screen.queryByText("Question text 0")).not.toBeInTheDocument();
    expect(screen.getByText(/Questions are hidden until both are back on/)).toBeInTheDocument();
  });

  test("red status when no face is detected", async () => {
    routes({ "POST /proctoring/frame": { face_detected: false, face_count: 0, gaze: null, warning: "No face detected." } });
    installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await enableMediaAndBegin();
    await screen.findByText("Question text 0");
    await act(async () => { jest.advanceTimersByTime(3000); });
    await waitFor(() => expect(screen.getByTestId("gaze-status")).toHaveAttribute("data-tone", "red"));
  });

  test("start errors are shown", async () => {
    routes({ "POST /exams/1/start": [409, { detail: "Exam already submitted" }] });
    installMediaDevices();
    withRouter(<ExamSitting id="1" />);
    await enableMediaAndBegin();
    expect(await screen.findByText("Exam already submitted")).toBeInTheDocument();
  });
});

describe("Proctor views (FR3, FR5)", () => {
  const report = {
    examination_id: 1,
    title: "Sample Quiz",
    students: [{
      student_id: 5, username: "student1", full_name: "Sam", attempt_status: "in_progress",
      incident_count: 3, incidents_by_type: { looking_away: 3 }, first_incident: "2025-01-01T10:00:00Z",
      last_incident: "2025-01-01T10:00:20Z", score: 4, max_score: 10, flagged: true,
      flag_reasons: ["3+ looking-away incidents within 30s"], pending_reviews: 3,
    }],
  };

  test("dashboard shows flagged students and polls", async () => {
    jest.useFakeTimers({ advanceTimers: true });
    loginAs("staff");
    const calls = mockFetch({ "GET /exams": [EXAM], "GET /reports/exams/1": report });
    withRouter(<ProctorDashboard />, "/proctor");
    expect(await screen.findByText("Flagged")).toBeInTheDocument();
    expect(screen.getByText("3 to review")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review" })).toHaveAttribute("href", "/proctor/exams/1/students/5");
    const before = calls.filter((c) => c.key === "GET /reports/exams/1").length;
    await act(async () => { jest.advanceTimersByTime(7000); });
    expect(calls.filter((c) => c.key === "GET /reports/exams/1").length).toBeGreaterThan(before);
    jest.useRealTimers();
  });

  test("dashboard empty state and exam switching", async () => {
    loginAs("staff");
    const other = { ...EXAM, id: 2, title: "Other", is_active: false };
    mockFetch({
      "GET /exams": [EXAM, other],
      "GET /reports/exams/1": { examination_id: 1, title: "Sample Quiz", students: [] },
      "GET /reports/exams/2": report,
    });
    withRouter(<ProctorDashboard />);
    expect(await screen.findByText(/No students have started/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "2" } });
    expect(await screen.findByText("Flagged")).toBeInTheDocument();
  });

  test("incident review shows evidence and records a human decision", async () => {
    loginAs("staff");
    const incident = {
      id: 9, student_id: 5, examination_id: 1, timestamp: "2025-01-01T10:00:00Z", incident_type: "looking_away",
      confidence: 0.91, review_status: "pending", reviewer_note: "", evidence_url: "http://minio/evidence/x.jpg?sig",
    };
    const calls = mockFetch({
      "GET /reports/exams/1/students/5": { examination_id: 1, student_id: 5, username: "student1", flagged: true,
        flag_reasons: ["3+ looking-away incidents within 30s"], incidents: [incident, { ...incident, id: 10, evidence_url: null, incident_type: "no_face" }] },
      "PATCH /reports/incidents/9": { ...incident, review_status: "needs_follow_up" },
    });
    withRouter(<IncidentReview examId="1" studentId="5" />);
    const img = await screen.findByAltText("Evidence for incident 9");
    expect(img).toHaveAttribute("src", incident.evidence_url);
    expect(screen.getByText(/No image/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /needs follow-up/i })[0]);
    expect(await screen.findByText("Needs follow-up", { selector: ".badge" })).toBeInTheDocument();
    expect(JSON.parse(calls.find((c) => c.key === "PATCH /reports/incidents/9").opts.body)).toEqual({ review_status: "needs_follow_up", note: "" });
  });
});

describe("App routing (AUTH-7)", () => {
  test("unauthenticated users are redirected to /login", async () => {
    const { location } = withRouter(<App />, "/exams");
    await waitFor(() => expect(location.history.at(-1)).toBe("/login"));
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  test("students cannot open the proctor dashboard", async () => {
    loginAs("student");
    mockFetch({ "GET /exams": [EXAM] });
    const { location } = withRouter(<App />, "/proctor");
    await waitFor(() => expect(location.history.at(-1)).toBe("/exams"));
  });

  test("staff opening a student route go to /proctor; logout clears session", async () => {
    loginAs("staff");
    mockFetch({ "GET /exams": [EXAM], "GET /reports/exams/1": { examination_id: 1, title: "t", students: [] } });
    const { location } = withRouter(<App />, "/exams");
    await waitFor(() => expect(location.history.at(-1)).toBe("/proctor"));
    await userEvent.click(screen.getByRole("button", { name: /log out/i }));
    await waitFor(() => expect(location.history.at(-1)).toBe("/login"));
    expect(sessionStorage.getItem("proctoring.token")).toBeNull();
  });

  test("unknown routes show not found", () => {
    withRouter(<App />, "/nope");
    expect(screen.getByText(/Page not found/)).toBeInTheDocument();
  });
});
