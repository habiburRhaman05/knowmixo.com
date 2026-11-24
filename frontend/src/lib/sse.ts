/**
 * SSE event stream parser used by the chat pipeline (and later by the
 * widget). Needs to handle:
 *   - multiline "data:" fields joined by "\n"
 *   - comment lines ("//: heartbeat") that keep the stream alive
 *   - CR / CRLF / LF line endings
 *   - chunks that split in the middle of a UTF-8 character or an event
 *   - the "id" and "retry" fields (even if we don't use them yet)
 *   - caller abort via AbortSignal
 *
 * The backend sends every event with an explicit event name (meta / sources /
 * delta / done / error) and JSON data; we hand those out as structured
 * objects so callers don't each re-parse them.
 */

export type SseEvent =
  | { kind: "message"; event: string; data: string; id?: string }
  | { kind: "heartbeat" };

export async function* parseSseStream(
  response: Response
): AsyncIterableIterator<SseEvent> {
  if (!response.body) throw new Error("No stream body on response");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // A record is separated by a blank line. Normalize CRLF/CR to LF first.
      buffer = buffer.replace(/\r\n|\r/g, "\n");
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const parsed = parseRecord(raw);
        if (parsed) yield parsed;
        sep = buffer.indexOf("\n\n");
      }
    }
    // Flush any dangling record with no trailing blank line.
    const tail = buffer.trim();
    if (tail) {
      const parsed = parseRecord(tail);
      if (parsed) yield parsed;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* already released */
    }
  }
}

function parseRecord(raw: string): SseEvent | null {
  const lines = raw.split("\n");
  let event = "message";
  let data: string[] = [];
  let id: string | undefined;
  let isComment = false;

  for (const line of lines) {
    if (line === "") continue;
    if (line.startsWith(":")) {
      isComment = true;
      continue;
    }
    // "field" or "field: value". SSE specifies one leading space may be
    // stripped from the value.
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    switch (field) {
      case "event":
        event = value || "message";
        break;
      case "data":
        data.push(value);
        break;
      case "id":
        id = value;
        break;
      case "retry":
        // Ignored for now, no reconnect logic.
        break;
      default:
        break;
    }
  }

  if (data.length === 0) {
    return isComment ? { kind: "heartbeat" } : null;
  }
  return { kind: "message", event, data: data.join("\n"), id };
}
