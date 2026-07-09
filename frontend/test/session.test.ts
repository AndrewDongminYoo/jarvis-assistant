import { canStartWakeListening, stepStatusLabel } from "../src/session.js";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
  }
}

assertEqual(canStartWakeListening("idle", false, false), false);
assertEqual(canStartWakeListening("idle", true, false), true);
assertEqual(canStartWakeListening("thinking", true, false), false);
assertEqual(canStartWakeListening("thinking", true, true), true);
assertEqual(canStartWakeListening("speaking", true, false), false);
assertEqual(canStartWakeListening("speaking", true, true), true);
assertEqual(
  stepStatusLabel({
    type: "step",
    kind: "CALENDAR",
    summary: "CALENDAR completed.",
  }),
  "CALENDAR completed.",
);
assertEqual(
  stepStatusLabel({ type: "step", kind: "BROWSE" }),
  "BROWSE completed.",
);
assertEqual(stepStatusLabel({ type: "step" }), "Working…");
