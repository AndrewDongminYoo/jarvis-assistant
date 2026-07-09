export type AppState = "idle" | "listening" | "thinking" | "speaking";

export function canStartWakeListening(
  state: AppState,
  activated: boolean,
  force: boolean,
): boolean {
  if (!activated) return false;
  if (force) return true;
  return state !== "thinking" && state !== "speaking";
}

export function stepStatusLabel(
  message: Readonly<Record<string, unknown>>,
): string {
  const summary = message["summary"];
  if (typeof summary === "string" && summary.trim()) return summary.trim();

  const kind = message["kind"];
  if (typeof kind === "string" && kind.trim()) {
    return `${kind.trim()} completed.`;
  }

  return "Working…";
}
