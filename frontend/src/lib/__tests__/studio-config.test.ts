import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, diffConfig } from "@/components/chatbot/studio-config";

describe("diffConfig", () => {
  it("returns an empty object when nothing changed", () => {
    expect(diffConfig(DEFAULT_CONFIG, DEFAULT_CONFIG)).toEqual({});
  });

  it("includes only the keys that actually changed", () => {
    const next = { ...DEFAULT_CONFIG, name: "Acme" };
    expect(diffConfig(next, DEFAULT_CONFIG)).toEqual({ name: "Acme" });
  });

  it("deep-compares nested branding", () => {
    const next = { ...DEFAULT_CONFIG, branding: { ...DEFAULT_CONFIG.branding, color: "#ff0000" } };
    expect(diffConfig(next, DEFAULT_CONFIG)).toEqual({
      branding: { color: "#ff0000", position: "bottom-right" },
    });
  });

  it("detects array changes (suggestions)", () => {
    const next = { ...DEFAULT_CONFIG, suggestions: ["Hello"] };
    expect(diffConfig(next, DEFAULT_CONFIG)).toEqual({ suggestions: ["Hello"] });
  });
});
