import { describe, expect, it } from "vitest";
import { ApiError, describeError } from "@/lib/errors";

describe("describeError", () => {
  it("maps known codes to a user-safe title/message", () => {
    const err = new ApiError(401, { code: "invalid_credentials", message: "x", request_id: "r-1" });
    const described = describeError(err);
    expect(described.code).toBe("invalid_credentials");
    expect(described.title).toBe("Incorrect email or password");
    expect(described.requestId).toBe("r-1");
  });

  it("falls back to a generic title for unknown codes", () => {
    const err = new ApiError(500, { code: "wobble" });
    const described = describeError(err);
    expect(described.title).toBe("Something went wrong");
  });

  it("handles non-ApiError inputs", () => {
    expect(describeError(new Error("boom")).message).toBe("boom");
    expect(describeError("nope").title).toBe("Something went wrong");
  });
});
