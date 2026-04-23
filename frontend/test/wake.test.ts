import { parseWakeCommand } from "../src/wake.js";

function assertDeepEqual(actual: unknown, expected: unknown): void {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`Expected ${expectedJson}, got ${actualJson}`);
  }
}

assertDeepEqual(parseWakeCommand("Jarvis, what's on my calendar?", false), {
  kind: "command",
  command: "what's on my calendar?",
});

assertDeepEqual(parseWakeCommand("hey jarvis open mail", false), {
  kind: "command",
  command: "open mail",
});

assertDeepEqual(parseWakeCommand("Hey, Jarvis open mail", false), {
  kind: "command",
  command: "open mail",
});

assertDeepEqual(parseWakeCommand("자비스 오늘 일정 알려줘", false), {
  kind: "command",
  command: "오늘 일정 알려줘",
});

assertDeepEqual(parseWakeCommand("헤이, 자비스 오늘 일정 알려줘", false), {
  kind: "command",
  command: "오늘 일정 알려줘",
});

assertDeepEqual(parseWakeCommand("Jarvis", false), {
  kind: "arm",
});

assertDeepEqual(parseWakeCommand("오늘 일정 알려줘", true), {
  kind: "command",
  command: "오늘 일정 알려줘",
});

assertDeepEqual(parseWakeCommand("오늘 일정 알려줘", false), {
  kind: "ignore",
});
