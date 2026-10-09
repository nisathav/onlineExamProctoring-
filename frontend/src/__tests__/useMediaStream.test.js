// Tests for the camera / screen-sharing hook, using fake devices (SCRN-x test IDs).
import { act, renderHook } from "@testing-library/react";
import useMediaStream, { describeMediaError } from "../hooks/useMediaStream";
import { fakeStream, installMediaDevices, namedError } from "./testUtils";

describe("useMediaStream (SCRN, FR2, FR6)", () => {
  afterEach(() => {
    delete window.isSecureContext;
  });

  test("SCRN-1: starts camera and full-screen share", async () => {
    const { mediaDevices, cam, scr } = installMediaDevices();
    const { result } = renderHook(() => useMediaStream());
    await act(() => result.current.startCamera());
    await act(() => result.current.startScreen());
    expect(mediaDevices.getUserMedia).toHaveBeenCalledWith(expect.objectContaining({ audio: false }));
    expect(result.current.camera).toBe(cam);
    expect(result.current.screen).toBe(scr);
    expect(result.current.errors).toEqual({ camera: null, screen: null });
  });

  test("SCRN-2: permission denied gives a clear message", async () => {
    installMediaDevices({ camera: namedError("NotAllowedError"), screen: namedError("NotAllowedError") });
    const { result } = renderHook(() => useMediaStream());
    await act(() => result.current.startCamera());
    await act(() => result.current.startScreen());
    expect(result.current.errors.camera).toMatch(/Permission for camera was denied/);
    expect(result.current.errors.screen).toMatch(/Permission for screen sharing was denied/);
    expect(result.current.camera).toBeNull();
  });

  test("SCRN-3: sharing a window instead of the whole screen is rejected", async () => {
    const windowShare = fakeStream({ displaySurface: "window" });
    installMediaDevices({ screen: windowShare });
    const { result } = renderHook(() => useMediaStream());
    await act(() => result.current.startScreen());
    expect(result.current.screen).toBeNull();
    expect(result.current.errors.screen).toMatch(/entire screen/);
    expect(windowShare.track.stop).toHaveBeenCalled();
  });

  test("SCRN-4: unsupported browser (e.g. no getDisplayMedia) and insecure context", async () => {
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: jest.fn() }, configurable: true });
    const { result } = renderHook(() => useMediaStream());
    await act(() => result.current.startScreen());
    expect(result.current.errors.screen).toMatch(/does not support screen sharing/);

    window.isSecureContext = false;
    await act(() => result.current.startCamera());
    expect(result.current.errors.camera).toMatch(/HTTPS/);
  });

  test("SCRN-5: stopping the share from the browser clears the stream and warns", async () => {
    const { scr } = installMediaDevices();
    const { result } = renderHook(() => useMediaStream());
    await act(() => result.current.startScreen());
    act(() => scr.track.fire("ended"));
    expect(result.current.screen).toBeNull();
    expect(result.current.errors.screen).toMatch(/Screen sharing stopped/);
  });

  test("stopAll stops every track, also on unmount", async () => {
    const { cam, scr } = installMediaDevices();
    const { result, unmount } = renderHook(() => useMediaStream());
    await act(() => result.current.startCamera());
    await act(() => result.current.startScreen());
    act(() => result.current.stopAll());
    expect(cam.track.stop).toHaveBeenCalled();
    expect(scr.track.stop).toHaveBeenCalled();
    expect(result.current.camera).toBeNull();
    unmount();
  });

  test("describeMediaError covers remaining cases", () => {
    expect(describeMediaError(namedError("NotFoundError"), "camera")).toMatch(/No camera/);
    expect(describeMediaError(namedError("NotFoundError"), "screen")).toMatch(/No screen/);
    expect(describeMediaError(namedError("NotReadableError"), "camera")).toMatch(/in use/);
    expect(describeMediaError(namedError("Unsupported"), "camera")).toMatch(/camera access/);
    expect(describeMediaError(new Error("boom"), "camera")).toMatch(/boom/);
  });
});
