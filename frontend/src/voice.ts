// voice.ts — Web Speech API capture + Web Audio playback queue
import { send } from "./ws.ts";

type LevelCb = (v: number) => void;
let recognition: SpeechRecognition | null = null;
let ctx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
const queue: AudioBuffer[] = [];
let playing = false;
let levelCb: LevelCb | null = null;
let rafId: number | null = null;

export function onLevel(cb: LevelCb): void {
  levelCb = cb;
}

function tickLevel(): void {
  if (!analyser || !levelCb) return;
  const data = new Uint8Array(analyser.frequencyBinCount);
  function loop(): void {
    analyser!.getByteFrequencyData(data);
    levelCb!(data.reduce((a, b) => a + b, 0) / data.length / 255);
    rafId = requestAnimationFrame(loop);
  }
  rafId = requestAnimationFrame(loop);
}

function stopLevel(): void {
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
}

async function getCtx(): Promise<AudioContext> {
  if (!ctx) {
    ctx = new AudioContext();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.connect(ctx.destination);
  }
  return ctx;
}

function playNext(): void {
  if (!ctx || !analyser || queue.length === 0) {
    playing = false;
    stopLevel();
    window.dispatchEvent(new Event("jarvis:speech-end"));
    return;
  }
  playing = true;
  tickLevel();
  const src = ctx.createBufferSource();
  src.buffer = queue.shift()!;
  src.connect(analyser);
  src.onended = playNext;
  src.start();
}

export async function enqueueAudio(b64: string): Promise<void> {
  const actx = await getCtx();
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const buf = await actx.decodeAudioData(bytes.buffer);
  queue.push(buf);
  if (!playing) playNext();
}

export function startListening(): void {
  type AnyWindow = Record<string, unknown>;
  const SR =
    ((window as unknown as AnyWindow)["SpeechRecognition"] as
      | typeof SpeechRecognition
      | undefined) ??
    ((window as unknown as AnyWindow)["webkitSpeechRecognition"] as
      | typeof SpeechRecognition
      | undefined);

  if (!SR) {
    console.error("Web Speech API requires Chrome");
    return;
  }
  recognition?.stop();
  recognition = new SR();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = "en-US";
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript.trim();
    if (text) {
      window.dispatchEvent(
        new CustomEvent("jarvis:transcript", { detail: text }),
      );
      send({ type: "transcript", text });
    }
  };
  recognition.onend = () =>
    window.dispatchEvent(new Event("jarvis:recognition-end"));
  recognition.onerror = () =>
    window.dispatchEvent(new Event("jarvis:recognition-end"));
  recognition.start();
}

export function stopListening(): void {
  recognition?.stop();
  recognition = null;
}

export function initAudio(): Promise<AudioContext> {
  return getCtx();
}
