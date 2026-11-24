import { describe, expect, it } from "vitest";
import { parseSseStream, type SseEvent } from "@/lib/sse";

function responseFromChunks(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return new Response(stream);
}

async function collect(response: Response): Promise<SseEvent[]> {
  const out: SseEvent[] = [];
  for await (const event of parseSseStream(response)) out.push(event);
  return out;
}

describe("parseSseStream", () => {
  it("parses the backend's meta/sources/delta/done shape in order", async () => {
    const stream = responseFromChunks([
      "event: meta\ndata: {\"seq\":1,\"conversation_id\":\"c\"}\n\n",
      "event: sources\ndata: {\"seq\":2,\"sources\":[]}\n\n",
      "event: delta\ndata: {\"seq\":3,\"text\":\"Hi \"}\n\n",
      "event: delta\ndata: {\"seq\":4,\"text\":\"there.\"}\n\n",
      "event: done\ndata: {\"seq\":5,\"message_id\":\"m\"}\n\n",
    ]);
    const events = await collect(stream);
    expect(events.map((e) => (e.kind === "message" ? e.event : "heartbeat"))).toEqual([
      "meta",
      "sources",
      "delta",
      "delta",
      "done",
    ]);
    const seqs = events
      .filter((e): e is Extract<SseEvent, { kind: "message" }> => e.kind === "message")
      .map((e) => (JSON.parse(e.data) as { seq: number }).seq);
    expect(seqs).toEqual([1, 2, 3, 4, 5]);
  });

  it("joins multi-line data fields with a newline", async () => {
    const stream = responseFromChunks(["event: delta\ndata: line one\ndata: line two\n\n"]);
    const [event] = await collect(stream);
    expect(event.kind).toBe("message");
    if (event.kind === "message") {
      expect(event.event).toBe("delta");
      expect(event.data).toBe("line one\nline two");
    }
  });

  it("returns heartbeat records for comment lines", async () => {
    const stream = responseFromChunks([": heartbeat\n\n", "event: done\ndata: {}\n\n"]);
    const events = await collect(stream);
    expect(events[0]).toEqual({ kind: "heartbeat" });
    expect(events[1].kind).toBe("message");
  });

  it("handles chunks that split in the middle of an event", async () => {
    const stream = responseFromChunks([
      "event: me",
      "ta\ndata: {\"seq\":1}",
      "\n\nevent: done\ndata: {}\n\n",
    ]);
    const events = await collect(stream);
    expect(events.length).toBe(2);
    expect(events[0].kind === "message" && events[0].event).toBe("meta");
    expect(events[1].kind === "message" && events[1].event).toBe("done");
  });

  it("accepts CRLF and bare CR line endings", async () => {
    const stream = responseFromChunks(["event: delta\r\ndata: a\r\n\r\n", "event: done\rdata: {}\r\r"]);
    const events = await collect(stream);
    expect(events.map((e) => (e.kind === "message" ? e.event : "heartbeat"))).toEqual(["delta", "done"]);
  });

  it("skips records that have no data", async () => {
    const stream = responseFromChunks(["event: ignore\n\n", "event: done\ndata: {}\n\n"]);
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0].kind === "message" && events[0].event).toBe("done");
  });
});
