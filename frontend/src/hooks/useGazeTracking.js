import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../services/api";

export const CAPTURE_INTERVAL_MS = 3000; // thesis: one frame every 3 seconds
const MAX_HISTORY = 50;

export function statusFromResult(result) {
  if (!result) return "idle";
  if (!result.face_detected) return "no_face";
  if (result.face_count > 1) return "multiple";
  if (result.gaze === "away") return "away";
  return "at";
}

// Grab the current webcam frame as a base64 JPEG (single frame, not video).
export function captureFrame(video, canvas) {
  if (!video || !video.videoWidth) return null;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.8);
}

export default function useGazeTracking(videoRef, examId, { enabled = true, intervalMs = CAPTURE_INTERVAL_MS, sendFrame = api.sendFrame } = {}) {
  const [latest, setLatest] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);
  const canvasRef = useRef(null);
  const inFlight = useRef(false);

  const tick = useCallback(async () => {
    if (inFlight.current) return; // never stack requests on a slow network
    if (!canvasRef.current) canvasRef.current = document.createElement("canvas");
    const image = captureFrame(videoRef.current, canvasRef.current);
    if (!image) return;
    inFlight.current = true;
    try {
      const result = await sendFrame(examId, image);
      setLatest(result);
      setError(null);
      if (result.warning) {
        setHistory((h) => [{ at: new Date().toISOString(), status: statusFromResult(result), warning: result.warning }, ...h].slice(0, MAX_HISTORY));
      }
    } catch (err) {
      setError(err.message || "Monitoring request failed");
    } finally {
      inFlight.current = false;
    }
  }, [videoRef, examId, sendFrame]);

  useEffect(() => {
    if (!enabled) return undefined;
    const id = setInterval(tick, intervalMs);
    return () => clearInterval(id);
  }, [enabled, intervalMs, tick]);

  return { latest, status: statusFromResult(latest), history, error };
}
