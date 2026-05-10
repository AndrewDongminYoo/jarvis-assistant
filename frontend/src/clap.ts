// clap.ts — Double-clap wake detector using Web Audio API
//
// Pure functions (isClap, isDoubleClap) hold the threshold logic so they can
// be unit-tested in Node without a browser. The exported start/stop functions
// own the AudioContext wiring, microphone stream, and RMS polling loop, and
// dispatch a `jarvis:double-clap` CustomEvent on `window` when two qualifying
// peaks land within the spec's window.

export const THRESHOLD = 0.25;
export const CLAP_MAX_MS = 150;
export const DOUBLE_WINDOW_MIN_MS = 80;
export const DOUBLE_WINDOW_MAX_MS = 800;
export const COOLDOWN_MS = 1000;

export const DOUBLE_CLAP_EVENT = "jarvis:double-clap";

const POLL_INTERVAL_MS = 16; // ~60 Hz

export function isClap(rms: number, durationMs: number): boolean {
  return rms > THRESHOLD && durationMs <= CLAP_MAX_MS;
}

export function isDoubleClap(firstMs: number, secondMs: number): boolean {
  const delta = secondMs - firstMs;
  return delta >= DOUBLE_WINDOW_MIN_MS && delta <= DOUBLE_WINDOW_MAX_MS;
}

let stream: MediaStream | null = null;
let source: MediaStreamAudioSourceNode | null = null;
let analyser: AnalyserNode | null = null;
let buf: Uint8Array<ArrayBuffer> | null = null;
let pollHandle: number | null = null;

let peakStart: number | null = null;
let peakMaxRms = 0;
let lastClapAt: number | null = null;
let cooldownUntil = 0;

function computeRms(samples: Uint8Array<ArrayBuffer>): number {
  let sumSq = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const v = (samples[i] - 128) / 128;
    sumSq += v * v;
  }
  return Math.sqrt(sumSq / samples.length);
}

function resetPeak(): void {
  peakStart = null;
  peakMaxRms = 0;
}

function poll(): void {
  if (!analyser || !buf) return;
  analyser.getByteTimeDomainData(buf);
  const rms = computeRms(buf);
  const now =
    typeof performance !== "undefined" ? performance.now() : Date.now();

  if (now < cooldownUntil) {
    resetPeak();
    return;
  }

  if (rms > THRESHOLD) {
    if (peakStart === null) peakStart = now;
    if (rms > peakMaxRms) peakMaxRms = rms;
    return;
  }

  if (peakStart !== null) {
    const duration = now - peakStart;
    const startedAt = peakStart;
    const maxRms = peakMaxRms;
    resetPeak();

    if (!isClap(maxRms, duration)) return;

    if (lastClapAt !== null && isDoubleClap(lastClapAt, startedAt)) {
      lastClapAt = null;
      cooldownUntil = now + COOLDOWN_MS;
      window.dispatchEvent(new Event(DOUBLE_CLAP_EVENT));
      return;
    }

    lastClapAt = startedAt;
    return;
  }

  if (lastClapAt !== null && now - lastClapAt > DOUBLE_WINDOW_MAX_MS) {
    lastClapAt = null;
  }
}

export async function startClapDetection(
  audioCtx: AudioContext,
): Promise<void> {
  if (analyser) return;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    console.warn("Clap detector: microphone unavailable", err);
    return;
  }
  source = audioCtx.createMediaStreamSource(stream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  buf = new Uint8Array(analyser.fftSize);
  pollHandle = window.setInterval(poll, POLL_INTERVAL_MS);
}

export function stopClapDetection(): void {
  if (pollHandle !== null) {
    window.clearInterval(pollHandle);
    pollHandle = null;
  }
  source?.disconnect();
  analyser?.disconnect();
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  source = null;
  analyser = null;
  buf = null;
  resetPeak();
  lastClapAt = null;
  cooldownUntil = 0;
}
