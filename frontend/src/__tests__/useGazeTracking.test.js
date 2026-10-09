// Tests for the 3-second frame capture hook, using fake timers (INT/FACE test IDs).
import { act, renderHook } from "@testing-library/react";
import useGazeTracking, { CAPTURE_INTERVAL_MS, captureFrame, statusFromResult } from "../hooks/useGazeTracking";

function fakeVideo() {
  return { current: { videoWidth: 640, videoHeight: 480 } };
}

beforeEach(() => {
  jest.useFakeTimers();
  HTMLCanvasElement.prototype.getContext = () => ({ drawImage: jest.fn() });
  HTMLCanvasElement.prototype.toDataURL = () => "data:image/jpeg;base64,AAA";
});
afterEach(() => jest.useRealTimers());

describe("useGazeTracking (FACE, INT)", () => {
  test("INT-1: captures one frame every 3 seconds and exposes status", async () => {
    const sendFrame = jest.fn().mockResolvedValue({ face_detected: true, face_count: 1, gaze: "at", warning: null });
    const { result } = renderHook(() => useGazeTracking(fakeVideo(), 7, { sendFrame }));
    expect(CAPTURE_INTERVAL_MS).toBe(3000);
    await act(async () => { jest.advanceTimersByTime(2999); });
    expect(sendFrame).not.toHaveBeenCalled();
    await act(async () => { jest.advanceTimersByTime(1); });
    expect(sendFrame).toHaveBeenCalledWith(7, "data:image/jpeg;base64,AAA");
    expect(result.current.status).toBe("at");
    expect(result.current.history).toHaveLength(0);
  });

  test("INT-3: warnings are kept in the incident history", async () => {
    const sendFrame = jest.fn().mockResolvedValue({ face_detected: true, face_count: 1, gaze: "away", warning: "look here" });
    const { result } = renderHook(() => useGazeTracking(fakeVideo(), 1, { sendFrame }));
    await act(async () => { jest.advanceTimersByTime(3000); });
    await act(async () => { jest.advanceTimersByTime(3000); });
    expect(result.current.status).toBe("away");
    expect(result.current.history).toHaveLength(2);
    expect(result.current.history[0]).toMatchObject({ status: "away", warning: "look here" });
  });

  test("does not stack requests while one is in flight", async () => {
    let resolve;
    const sendFrame = jest.fn(() => new Promise((r) => { resolve = r; }));
    renderHook(() => useGazeTracking(fakeVideo(), 1, { sendFrame }));
    await act(async () => { jest.advanceTimersByTime(9000); });
    expect(sendFrame).toHaveBeenCalledTimes(1);
    await act(async () => { resolve({ face_detected: true, face_count: 1, gaze: "at" }); });
  });

  test("disabled hook sends nothing; errors are reported", async () => {
    const sendFrame = jest.fn().mockRejectedValue(new Error("offline"));
    const { result, rerender } = renderHook(({ enabled }) => useGazeTracking(fakeVideo(), 1, { enabled, sendFrame }), {
      initialProps: { enabled: false },
    });
    await act(async () => { jest.advanceTimersByTime(6000); });
    expect(sendFrame).not.toHaveBeenCalled();
    rerender({ enabled: true });
    await act(async () => { jest.advanceTimersByTime(3000); });
    expect(result.current.error).toBe("offline");
  });

  test("FACE-8: statusFromResult maps API results to indicator states", () => {
    expect(statusFromResult(null)).toBe("idle");
    expect(statusFromResult({ face_detected: false, face_count: 0 })).toBe("no_face");
    expect(statusFromResult({ face_detected: true, face_count: 2 })).toBe("multiple");
    expect(statusFromResult({ face_detected: true, face_count: 1, gaze: "away" })).toBe("away");
    expect(statusFromResult({ face_detected: true, face_count: 1, gaze: null })).toBe("at");
  });

  test("captureFrame skips when the video has no frames yet", () => {
    expect(captureFrame({ videoWidth: 0 }, document.createElement("canvas"))).toBeNull();
    expect(captureFrame(null, document.createElement("canvas"))).toBeNull();
  });
});
