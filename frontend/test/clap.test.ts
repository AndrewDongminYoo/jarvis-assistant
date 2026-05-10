import { isClap, isDoubleClap } from "../src/clap.js";

function assertEqual(actual: boolean, expected: boolean, label: string): void {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

// isClap — strong short peak
assertEqual(isClap(0.3, 80), true, "strong short peak");

// isClap — too quiet
assertEqual(isClap(0.1, 80), false, "too quiet");

// isClap — too long (voice, not clap)
assertEqual(isClap(0.4, 200), false, "too long (voice)");

// isDoubleClap — valid double
assertEqual(isDoubleClap(0, 400), true, "valid double");

// isDoubleClap — too slow
assertEqual(isDoubleClap(0, 900), false, "too slow");

// isDoubleClap — too fast (single peak artifact)
assertEqual(isDoubleClap(0, 30), false, "too fast");
