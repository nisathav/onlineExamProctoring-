import { useCallback, useEffect, useRef, useState } from "react";

// Maps getUserMedia/getDisplayMedia failures to messages a student can act on.
export function describeMediaError(err, kind) {
  const what = kind === "screen" ? "screen sharing" : "camera";
  switch (err?.name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
      return `Permission for ${what} was denied. Allow it in your browser settings and try again.`;
    case "NotFoundError":
      return kind === "screen" ? "No screen is available to share." : "No camera was found on this device.";
    case "NotReadableError":
      return `Your ${what} is in use by another application.`;
    case "InsecureContext":
      return "Camera and screen sharing need a secure (HTTPS) connection.";
    case "Unsupported":
      return kind === "screen"
        ? "This browser does not support screen sharing. Please use Chrome, Edge or Firefox."
        : "This browser does not support camera access.";
    default:
      return `Could not start ${what}: ${err?.message || "unknown error"}`;
  }
}

function checkSupport(kind) {
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    const e = new Error("insecure");
    e.name = "InsecureContext";
    throw e;
  }
  const md = navigator.mediaDevices;
  const fn = kind === "screen" ? md?.getDisplayMedia : md?.getUserMedia;
  if (!fn) {
    const e = new Error("unsupported");
    e.name = "Unsupported";
    throw e;
  }
}

function stopStream(stream) {
  stream?.getTracks().forEach((t) => t.stop());
}

export default function useMediaStream() {
  const [camera, setCamera] = useState(null);
  const [screen, setScreen] = useState(null);
  const [errors, setErrors] = useState({ camera: null, screen: null });
  const cameraRef = useRef(null);
  const screenRef = useRef(null);

  const startCamera = useCallback(async () => {
    try {
      checkSupport("camera");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
        audio: false,
      });
      cameraRef.current = stream;
      setCamera(stream);
      setErrors((e) => ({ ...e, camera: null }));
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        cameraRef.current = null;
        setCamera(null);
        setErrors((e) => ({ ...e, camera: "Your camera stopped. Please restart it to continue." }));
      });
      return stream;
    } catch (err) {
      setErrors((e) => ({ ...e, camera: describeMediaError(err, "camera") }));
      return null;
    }
  }, []);

  const startScreen = useCallback(async () => {
    try {
      checkSupport("screen");
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: "monitor" },
        audio: false,
      });
      const surface = stream.getVideoTracks()[0]?.getSettings?.().displaySurface;
      if (surface && surface !== "monitor") {
        stopStream(stream);
        setErrors((e) => ({ ...e, screen: "Please share your entire screen, not a window or tab." }));
        return null;
      }
      screenRef.current = stream;
      setScreen(stream);
      setErrors((e) => ({ ...e, screen: null }));
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        screenRef.current = null;
        setScreen(null);
        setErrors((e) => ({ ...e, screen: "Screen sharing stopped. Share your screen again to continue." }));
      });
      return stream;
    } catch (err) {
      setErrors((e) => ({ ...e, screen: describeMediaError(err, "screen") }));
      return null;
    }
  }, []);

  const stopAll = useCallback(() => {
    stopStream(cameraRef.current);
    stopStream(screenRef.current);
    cameraRef.current = null;
    screenRef.current = null;
    setCamera(null);
    setScreen(null);
  }, []);

  useEffect(() => stopAll, [stopAll]);

  return { camera, screen, errors, startCamera, startScreen, stopAll };
}
