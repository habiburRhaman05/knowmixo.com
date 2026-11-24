import { describe, expect, it } from "vitest";
import { ERROR_CODE_COPY, STATUS_META, STAGE_LABEL } from "@/lib/types";

/**
 * A few targeted checks that stop status/stage/error maps drifting into
 * wrong keys or missing labels, which would break the Knowledge UI
 * silently (status badges reading "undefined").
 */

describe("status metadata", () => {
  it("has a label and tone for every document status", () => {
    const required = ["pending", "processing", "retrying", "quota_wait", "ready", "failed", "retired"];
    for (const key of required) {
      const meta = STATUS_META[key as keyof typeof STATUS_META];
      expect(meta, `missing status: ${key}`).toBeDefined();
      expect(meta.label.length).toBeGreaterThan(0);
      expect(["ready", "processing", "waiting", "failed", "idle"]).toContain(meta.tone);
    }
  });

  it("has a label for every stage name", () => {
    for (const stage of ["validate", "extract", "chunk", "embed", "upsert", "finalize"] as const) {
      expect(STAGE_LABEL[stage].length).toBeGreaterThan(0);
    }
  });
});

describe("error_code copy", () => {
  it("covers every backend error code the Knowledge UI can surface", () => {
    const expected = [
      "unsupported_scanned_pdf",
      "unsupported_file_type",
      "file_too_large",
      "extraction_empty",
      "ssrf_blocked",
      "quota_exhausted",
      "embedding_quota_exhausted",
      "checksum_mismatch",
      "grant_expired",
      "file_signature_mismatch",
      "no_pages_discovered",
      "crawl_not_ready",
      "page_not_discovered",
    ];
    for (const code of expected) {
      expect(ERROR_CODE_COPY[code], `missing user copy for code: ${code}`).toBeTruthy();
    }
  });

  it("messages don't leak error_code tokens like underscores", () => {
    for (const [code, msg] of Object.entries(ERROR_CODE_COPY)) {
      expect(msg, `empty message for ${code}`).toBeTruthy();
      expect(msg, `raw code leaked into user copy for ${code}`).not.toMatch(/^[a-z_]+$/);
    }
  });
});
