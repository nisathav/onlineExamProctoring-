// Fetch wrapper: attaches the JWT, redirects to /login on 401. Tokens never go in URLs.
export const API_URL = globalThis.__API_URL__ || "http://localhost:8000";

const TOKEN_KEY = "proctoring.token";
const USER_KEY = "proctoring.user";

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.status = status;
    this.detail = detail;
  }
}

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getUser() {
  const raw = sessionStorage.getItem(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function setSession(token, user) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
}

let onUnauthorized = () => {
  window.location.assign("/login");
};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export async function request(path, { method = "GET", body, form, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } };
  const token = getToken();
  if (token) opts.headers.Authorization = `Bearer ${token}`;
  if (form) {
    opts.body = form;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(`${API_URL}${path}`, opts);
  if (res.status === 401 && path !== "/auth/token") {
    clearSession();
    onUnauthorized();
    throw new ApiError(401, "Session expired, please log in again");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    throw new ApiError(res.status, Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : detail);
  }
  return data;
}

export async function login(username, password) {
  // OAuth2 password flow expects form-encoded fields.
  const form = new URLSearchParams({ username, password });
  const data = await request("/auth/token", { method: "POST", form });
  setSession(data.access_token, { username: data.username, role: data.role });
  return data;
}

export function logout() {
  clearSession();
}

export const api = {
  exams: () => request("/exams"),
  exam: (id) => request(`/exams/${id}`),
  consent: () => request("/auth/consent"),
  giveConsent: () => request("/auth/consent", { method: "POST" }),
  startExam: (id) => request(`/exams/${id}/start`, { method: "POST" }),
  question: (id, index) => request(`/exams/${id}/questions/${index}`),
  answer: (id, questionId, answer) =>
    request(`/exams/${id}/answers`, { method: "POST", body: { question_id: questionId, answer } }),
  submitExam: (id) => request(`/exams/${id}/submit`, { method: "POST" }),
  progress: (id) => request(`/exams/${id}/progress`),
  sendFrame: (examId, image) =>
    request("/proctoring/frame", { method: "POST", body: { exam_id: examId, image } }),
  examReport: (id) => request(`/reports/exams/${id}`),
  studentTimeline: (examId, studentId) => request(`/reports/exams/${examId}/students/${studentId}`),
  reviewIncident: (id, reviewStatus, note = "") =>
    request(`/reports/incidents/${id}`, { method: "PATCH", body: { review_status: reviewStatus, note } }),
};
