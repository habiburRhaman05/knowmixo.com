import { describe, expect, it } from "vitest";
import { readParentOrigin, readVisitorToken } from "@/lib/widget-backend";

function request(headers: Record<string, string>): Request {
  return new Request("http://localhost/x", { headers });
}

describe("widget-backend helpers", () => {
  it("reads a bearer visitor token", () => {
    expect(readVisitorToken(request({ authorization: "Bearer abc.def" }))).toBe("abc.def");
    expect(readVisitorToken(request({ authorization: "bearer whitespace " }))).toBe("whitespace");
  });

  it("rejects non-bearer and missing authorization", () => {
    expect(readVisitorToken(request({}))).toBeNull();
    expect(readVisitorToken(request({ authorization: "Basic abc" }))).toBeNull();
    expect(readVisitorToken(request({ authorization: "Bearer " }))).toBeNull();
  });

  it("prefers x-parent-origin over referer", () => {
    expect(
      readParentOrigin(
        request({ "x-parent-origin": "https://host.example", referer: "https://other" })
      )
    ).toBe("https://host.example");
    expect(readParentOrigin(request({ referer: "https://only-referer" }))).toBe(
      "https://only-referer"
    );
    expect(readParentOrigin(request({}))).toBeNull();
  });
});
