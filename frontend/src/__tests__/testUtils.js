// Shared mocks for media devices and fetch.
export function fakeTrack(settings = {}) {
  const listeners = {};
  return {
    stop: jest.fn(),
    getSettings: () => settings,
    addEventListener: (ev, fn) => { listeners[ev] = fn; },
    fire: (ev) => listeners[ev]?.(),
  };
}

export function fakeStream(settings) {
  const track = fakeTrack(settings);
  return { track, getTracks: () => [track], getVideoTracks: () => [track] };
}

export function installMediaDevices({ camera, screen } = {}) {
  const cam = camera ?? fakeStream();
  const scr = screen ?? fakeStream({ displaySurface: "monitor" });
  const mediaDevices = {
    getUserMedia: jest.fn(() => (cam instanceof Error ? Promise.reject(cam) : Promise.resolve(cam))),
    getDisplayMedia: jest.fn(() => (scr instanceof Error ? Promise.reject(scr) : Promise.resolve(scr))),
  };
  Object.defineProperty(navigator, "mediaDevices", { value: mediaDevices, configurable: true });
  return { mediaDevices, cam, scr };
}

export function namedError(name, message = name) {
  const e = new Error(message);
  e.name = name;
  return e;
}

export function jsonResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  });
}

// Route-table fetch mock: { "GET /exams": data | (body) => data | [status, data] }
export function mockFetch(routes) {
  const calls = [];
  global.fetch = jest.fn((url, opts = {}) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const key = `${opts.method || "GET"} ${path}`;
    calls.push({ key, opts });
    let handler = routes[key];
    if (handler === undefined) return jsonResponse({ detail: `no mock for ${key}` }, 500);
    if (typeof handler === "function") handler = handler(opts.body ? JSON.parse(opts.body) : undefined, opts);
    if (Array.isArray(handler) && typeof handler[0] === "number") return jsonResponse(handler[1], handler[0]);
    return jsonResponse(handler);
  });
  return calls;
}

export function loginAs(role = "student", username = role === "staff" ? "staff1" : "student1") {
  sessionStorage.setItem("proctoring.token", "tok");
  sessionStorage.setItem("proctoring.user", JSON.stringify({ username, role }));
}
