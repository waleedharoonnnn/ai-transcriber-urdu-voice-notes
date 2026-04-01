import React, { useEffect, useMemo, useRef, useState } from "react";

const statusCycle = [
  "Converting urdu to text...",
  "Translating to English...",
  "Summarizing Note...",
  "Saving to database...",
];

function formatMs(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export default function Recorder({ onCreate }) {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingText, setProcessingText] = useState(statusCycle[0]);
  const [error, setError] = useState(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const startedAtRef = useRef(null);
  const intervalRef = useRef(null);
  const animFrameRef = useRef(null);

  const canvasRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const streamRef = useRef(null);

  const cycleText = useMemo(() => {
    let idx = 0;
    return () => {
      const text = statusCycle[idx % statusCycle.length];
      idx += 1;
      return text;
    };
  }, []);

  function stopTimers() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
  }

  function cleanupAudioGraph() {
    try {
      if (sourceRef.current) sourceRef.current.disconnect();
      if (analyserRef.current) analyserRef.current.disconnect();
    } catch {
      // ignore
    }
    sourceRef.current = null;
    analyserRef.current = null;

    if (audioCtxRef.current) {
      try {
        audioCtxRef.current.close();
      } catch {
        // ignore
      }
      audioCtxRef.current = null;
    }
  }

  function stopStreamTracks() {
    if (streamRef.current) {
      for (const t of streamRef.current.getTracks()) t.stop();
    }
    streamRef.current = null;
  }

  useEffect(() => {
    return () => {
      stopTimers();
      cleanupAudioGraph();
      stopStreamTracks();
    };
  }, []);

  function drawWaveform() {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth * dpr;
    const height = canvas.clientHeight * dpr;

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    const bufferLength = analyser.fftSize;
    const dataArray = new Uint8Array(bufferLength);
    analyser.getByteTimeDomainData(dataArray);

    ctx.clearRect(0, 0, width, height);
    ctx.lineWidth = 2 * dpr;
    ctx.strokeStyle = "#a1a1aa"; // zinc-400
    ctx.beginPath();

    const sliceWidth = width / bufferLength;
    let x = 0;

    for (let i = 0; i < bufferLength; i++) {
      const v = dataArray[i] / 128.0;
      const y = (v * height) / 2;

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);

      x += sliceWidth;
    }

    ctx.lineTo(width, height / 2);
    ctx.stroke();

    animFrameRef.current = requestAnimationFrame(drawWaveform);
  }

  async function startRecording() {
    setError(null);

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorderRef.current = mediaRecorder;
    chunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };

    mediaRecorder.start();
    setIsRecording(true);
    startedAtRef.current = Date.now();

    intervalRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current);
    }, 250);

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    audioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    sourceRef.current = source;
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    analyserRef.current = analyser;
    source.connect(analyser);

    drawWaveform();
  }

  async function stopRecording() {
    setError(null);

    const mediaRecorder = mediaRecorderRef.current;
    if (!mediaRecorder) return;

    stopTimers();
    setIsRecording(false);
    setElapsedMs(0);

    const blob = await new Promise((resolve) => {
      mediaRecorder.onstop = () => {
        const b = new Blob(chunksRef.current, { type: "audio/webm" });
        resolve(b);
      };
      mediaRecorder.stop();
    });

    cleanupAudioGraph();
    stopStreamTracks();

    setIsProcessing(true);
    setProcessingText(statusCycle[0]);

    const cycle = setInterval(() => {
      setProcessingText(cycleText());
    }, 900);

    try {
      await onCreate?.(blob);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        err?.message ||
        "Failed to create note";
      setError(msg);
    } finally {
      clearInterval(cycle);
      setIsProcessing(false);
      setProcessingText(statusCycle[0]);
    }
  }

  async function onMainClick() {
    try {
      if (isProcessing) return;
      if (!isRecording) await startRecording();
      else await stopRecording();
    } catch (err) {
      const msg = err?.message || "Microphone permission error";
      setError(msg);
      setIsRecording(false);
      stopTimers();
      cleanupAudioGraph();
      stopStreamTracks();
    }
  }

  return (
    <div className="w-full">
      <div className="flex items-center justify-center">
        <button
          type="button"
          onClick={onMainClick}
          className={
            "w-24 h-24 rounded-full flex items-center justify-center bg-white text-black font-semibold " +
            (isRecording ? "animate-[recPulse_1.5s_infinite]" : "") +
            (isProcessing ? " opacity-60" : "")
          }
          aria-label={isRecording ? "Stop recording" : "Start recording"}
        >
          {isRecording ? "Stop" : isProcessing ? "…" : "Rec"}
        </button>
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between text-sm text-zinc-400">
          <div>
            {isRecording ? "Recording" : isProcessing ? "Processing" : "Idle"}
          </div>
          <div>{isRecording ? formatMs(elapsedMs) : null}</div>
        </div>

        <div className="mt-2 h-16 bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <canvas ref={canvasRef} className="w-full h-full" />
        </div>

        {isProcessing ? (
          <div className="mt-3 text-sm text-zinc-300 text-center">
            {processingText}
          </div>
        ) : null}

        {error ? (
          <div className="mt-3 text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
            {String(error)}
          </div>
        ) : null}
      </div>
    </div>
  );
}
