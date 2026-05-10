// main.ts — JARVIS frontend state machine
import { connect, on, send } from "./ws.ts";
import {
  enqueueAudio,
  initAudio,
  onLevel,
  startListening,
  stopListening,
} from "./voice.ts";
import { parseWakeCommand } from "./wake.ts";
import { canStartWakeListening, type AppState } from "./session.ts";
import { init as initOrb, setAudioLevel, setState } from "./orb.ts";
import { initSettings } from "./settings.ts";
import { DOUBLE_CLAP_EVENT, startClapDetection } from "./clap.ts";

const TODAY_REPORT_DATE_KEY = "jarvis_today_report_date";

let state: AppState = "idle";
let activated = false;
let armed = false;
let receivedAudio = false;
const statusEl = document.getElementById("status")!;
const transcriptEl = document.getElementById("transcript")!;
const responseEl = document.getElementById("response")!;

const STATUS_TEXT: Record<AppState, string> = {
  idle: 'Click once, then say "Jarvis"',
  listening: 'Say "Jarvis"',
  thinking: "Thinking…",
  speaking: "Speaking…",
};

function transition(next: AppState, label?: string): void {
  state = next;
  statusEl.textContent = label ?? STATUS_TEXT[next];
  statusEl.className = next === "idle" ? "" : next;
  setState(next);
}

function startWakeListening(force = false): void {
  if (!canStartWakeListening(state, activated, force)) return;
  transition("listening", armed ? "Listening…" : STATUS_TEXT.listening);
  startListening();
}

function activateAssistant(): void {
  if (activated) return;
  activated = true;
  armed = false;
  responseEl.textContent = "";
  startWakeListening();
}

function sendCommand(command: string): void {
  armed = false;
  stopListening();
  transition("thinking");
  send({ type: "transcript", text: command });
}

on("connected", () => {
  if (activated) startWakeListening();
  else transition("idle");
});
on("disconnected", () => {
  statusEl.textContent = "Reconnecting…";
  statusEl.className = "error";
});
on("thinking", () => {
  receivedAudio = false;
  transition("thinking");
  stopListening();
});
on("text", (m) => {
  responseEl.textContent = (m["content"] as string) ?? "";
});
on("audio", (m) => {
  receivedAudio = true;
  void enqueueAudio(m["data"] as string);
  transition("speaking");
});
on("done", () => {
  if (!receivedAudio) startWakeListening(true);
});
on("error", (m) => {
  statusEl.textContent = `Error: ${m["message"] as string}`;
  statusEl.className = "error";
  window.setTimeout(() => startWakeListening(true), 1200);
});

window.addEventListener("jarvis:transcript", (e) => {
  const text = (e as CustomEvent<string>).detail;
  transcriptEl.textContent = text;
  const parsed = parseWakeCommand(text, armed);
  if (parsed.kind === "ignore") return;
  if (parsed.kind === "arm") {
    armed = true;
    transition("listening", "Listening…");
    return;
  }
  transcriptEl.textContent = parsed.command;
  sendCommand(parsed.command);
});
window.addEventListener("jarvis:recognition-end", () => {
  if (activated && state === "listening") {
    window.setTimeout(startWakeListening, 250);
  }
});
window.addEventListener("jarvis:speech-end", () => startWakeListening(true));

window.addEventListener(DOUBLE_CLAP_EVENT, () => {
  if (!activated) return;
  if (state === "thinking" || state === "speaking") return;

  const today = new Date().toDateString();
  if (localStorage.getItem(TODAY_REPORT_DATE_KEY) !== today) {
    localStorage.setItem(TODAY_REPORT_DATE_KEY, today);
    stopListening();
    transition("thinking");
    send({ type: "today-report" });
    return;
  }

  armed = true;
  transition("listening", "Listening…");
  startWakeListening(true);
});

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
    const audioCtx = await initAudio();
    void startClapDetection(audioCtx);
    activateAssistant();
  });
});
