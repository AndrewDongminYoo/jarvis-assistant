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
