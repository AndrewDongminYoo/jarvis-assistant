import { saveProviderPreference } from "../src/settings.js";

function assertDeepEqual(actual: unknown, expected: unknown): void {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`Expected ${expectedJson}, got ${actualJson}`);
  }
}

const failedResponse = await saveProviderPreference(
  "openai",
  "gemini",
  async () => new Response(null, { status: 500 }),
);
assertDeepEqual(failedResponse, { ok: false, preferred: "gemini" });

const failedRequest = await saveProviderPreference(
  "openai",
  "gemini",
  async () => Promise.reject(new TypeError("network unavailable")),
);
assertDeepEqual(failedRequest, { ok: false, preferred: "gemini" });

const savedResponse = await saveProviderPreference(
  "openai",
  "gemini",
  async () => new Response(null, { status: 200 }),
);
assertDeepEqual(savedResponse, { ok: true, preferred: "openai" });
