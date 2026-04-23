export type WakeCommand =
  | { kind: "ignore" }
  | { kind: "arm" }
  | { kind: "command"; command: string };

const WAKE_PATTERNS = [
  /^\s*(?:hey[\s,.:;!?-]+)?jarvis\b[\s,.:;!?-]*/i,
  /^\s*(?:헤이[\s,.:;!?-]+)?자비스(?:\s+|[,.:;!?-]+|$)/i,
];

export function parseWakeCommand(text: string, armed: boolean): WakeCommand {
  const normalized = text.trim();
  if (!normalized) return { kind: "ignore" };

  for (const pattern of WAKE_PATTERNS) {
    const withoutWake = normalized.replace(pattern, "").trim();
    if (withoutWake !== normalized) {
      return withoutWake
        ? { kind: "command", command: withoutWake }
        : { kind: "arm" };
    }
  }

  return armed ? { kind: "command", command: normalized } : { kind: "ignore" };
}
