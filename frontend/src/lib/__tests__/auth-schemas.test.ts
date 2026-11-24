import { describe, expect, it } from "vitest";
import {
  signupSchema,
  loginSchema,
  resetSchema,
  changePasswordSchema,
} from "@/lib/auth-schemas";

describe("auth schemas", () => {
  it("requires a 10+ character password on signup", () => {
    const r = signupSchema.safeParse({
      email: "a@b.co",
      password: "short",
      name: "A",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues.some((i) => i.path[0] === "password")).toBe(true);
    }
  });

  it("accepts a sensible signup payload", () => {
    const r = signupSchema.safeParse({
      email: "a@example.com",
      password: "correct-horse-battery",
      name: "Alex",
    });
    expect(r.success).toBe(true);
  });

  it("rejects malformed emails on login", () => {
    const r = loginSchema.safeParse({ email: "not-an-email", password: "x" });
    expect(r.success).toBe(false);
  });

  it("flags mismatched reset passwords on confirm_password", () => {
    const r = resetSchema.safeParse({
      token: "abc",
      new_password: "correct-horse-battery",
      confirm_password: "mismatch-long-enough",
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues.some((i) => i.path[0] === "confirm_password")).toBe(true);
    }
  });

  it("flags mismatched change-password confirm", () => {
    const r = changePasswordSchema.safeParse({
      current_password: "old-password-x",
      new_password: "correct-horse-battery",
      confirm_password: "mismatch-long-enough",
    });
    expect(r.success).toBe(false);
  });
});
