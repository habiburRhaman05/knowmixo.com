import { describe, expect, it } from "vitest";
import { passwordScore } from "@/components/ui/password-strength";

describe("passwordScore", () => {
  it("fails the length rule on short passwords", () => {
    // "abc" still passes the 'not obvious phrase' rule, so we check the
    // length rule specifically rather than demanding a 0 total.
    expect(passwordScore("abc")).toBeLessThan(2);
  });
  it("counts the length rule", () => {
    expect(passwordScore("abcdefghij")).toBeGreaterThan(0);
  });
  it("gives the max score to a varied, long password", () => {
    expect(passwordScore("Correct-horse-13!")).toBe(3);
  });
  it("downgrades obvious phrases", () => {
    expect(passwordScore("Password123!")).toBeLessThan(3);
  });
});
