// Tests for services/api.js: login, attaching the token, handling expired sessions and
// error messages.
import { api, getToken, getUser, login, request, setUnauthorizedHandler } from "../services/api";
import { mockFetch } from "./testUtils";

describe("services/api (AUTH, SEC)", () => {
  test("AUTH-3: login posts form data and stores the token", async () => {
    const calls = mockFetch({ "POST /auth/token": { access_token: "abc", role: "student", username: "s1" } });
    await login("s1", "pw");
    expect(calls[0].opts.body).toBeInstanceOf(URLSearchParams);
    expect(calls[0].opts.body.toString()).toBe("username=s1&password=pw");
    expect(getToken()).toBe("abc");
    expect(getUser()).toEqual({ username: "s1", role: "student" });
  });

  test("SEC-1: attaches bearer header, never puts token in the URL", async () => {
    sessionStorage.setItem("proctoring.token", "secret");
    mockFetch({ "GET /exams": [] });
    await api.exams();
    const [url, opts] = global.fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBe("Bearer secret");
    expect(url).not.toContain("secret");
  });

  test("SEC-3: 401 clears the session and redirects to login", async () => {
    sessionStorage.setItem("proctoring.token", "old");
    const handler = jest.fn();
    setUnauthorizedHandler(handler);
    mockFetch({ "GET /exams": [401, { detail: "expired" }] });
    await expect(api.exams()).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalled();
    expect(getToken()).toBeNull();
  });

  test("errors surface the API detail, including validation lists", async () => {
    mockFetch({
      "POST /exams/1/answers": [422, { detail: [{ msg: "bad answer" }, { msg: "other" }] }],
      "POST /exams/1/start": [403, { detail: "Proctoring consent required" }],
    });
    await expect(api.answer(1, 2, "x")).rejects.toThrow("bad answer; other");
    await expect(api.startExam(1)).rejects.toThrow("Proctoring consent required");
  });

  test("sendFrame posts JSON with exam id and image", async () => {
    const calls = mockFetch({ "POST /proctoring/frame": { face_detected: true } });
    await api.sendFrame(3, "data:image/jpeg;base64,AAA");
    expect(JSON.parse(calls[0].opts.body)).toEqual({ exam_id: 3, image: "data:image/jpeg;base64,AAA" });
    expect(calls[0].opts.headers["Content-Type"]).toBe("application/json");
  });

  test("204 responses resolve to null", async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, status: 204, json: () => Promise.reject() }));
    await expect(request("/questions/1", { method: "DELETE" })).resolves.toBeNull();
  });
});
