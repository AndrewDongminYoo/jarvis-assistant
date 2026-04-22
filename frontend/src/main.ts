// main.ts — JARVIS frontend state machine
import { connect, on, send } from "./ws.ts";
import {
  enqueueAudio,
  initAudio,
  onLevel,
  startListening,
  stopListening,
} from "./voice.ts";
import { init as initOrb, setAudioLevel, setState } from "./orb.ts";
import { initSettings } from "./settings.ts";

type State = "idle" | "listening" | "thinking" | "speaking";

let state: State = "idle";
const statusEl = document.getElementById("status")!;
const transcriptEl = document.getElementById("transcript")!;
const responseEl = document.getElementById("response")!;

const STATUS_TEXT: Record<State, string> = {
  idle: "Click to begin",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
};

function transition(next: State): void {
  state = next;
  statusEl.textContent = STATUS_TEXT[next];
  statusEl.className = next === "idle" ? "" : next;
  setState(next);
}

function startSession(): void {
  if (state !== "idle") return;
  transition("listening");
  startListening();
}

on("connected", () => transition("idle"));
on("disconnected", () => {
  statusEl.textContent = "Reconnecting…";
  statusEl.className = "error";
});
on("thinking", () => {
  transition("thinking");
  stopListening();
});
on("text", (m) => {
  responseEl.textContent = (m["content"] as string) ?? "";
});
on("audio", (m) => {
  void enqueueAudio(m["data"] as string);
  transition("speaking");
});
on("done", () => transition("idle"));
on("error", (m) => {
  statusEl.textContent = `Error: ${m["message"] as string}`;
  statusEl.className = "error";
});

window.addEventListener("jarvis:transcript", (e) => {
  transcriptEl.textContent = (e as CustomEvent<string>).detail;
});
window.addEventListener("jarvis:recognition-end", () => {
  if (state === "listening") send({ type: "abort" });
});
window.addEventListener("jarvis:speech-end", () => transition("idle"));

onLevel((v) => setAudioLevel(v));

window.addEventListener("DOMContentLoaded", async () => {
  const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  initOrb(canvas);
  initSettings();
  connect();

  document.body.addEventListener("click", async (e) => {
    if ((e.target as HTMLElement).closest("#settings-panel, #settings-btn"))
      return;
    await initAudio();
    startSession();
  });
});
