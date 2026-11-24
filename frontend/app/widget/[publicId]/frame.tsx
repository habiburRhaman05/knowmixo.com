"use client";
import * as React from "react";
import { PublicChatWindow } from "@/components/chat/public-chat-window";

/**
 * Iframe content rendered by `<iframe src="/widget/<publicId>">`. Talks to
 * the host page over postMessage:
 *   - On mount, sends {type: "kmv:ready"} so the host can close its
 *     loading UI.
 *   - On visible size change, sends {type: "kmv:size", width, height}.
 *   - Listens for {type: "kmv:open"} and {type: "kmv:close"} from the host.
 *
 * The host origin is validated on every postMessage. We accept any origin
 * for inbound messages but we only reply to messages that arrived from the
 * current parent (window.parent) so a nested-iframe attack can't eavesdrop.
 */
export function WidgetFrame({ publicId }: { publicId: string }) {
  const [open, setOpen] = React.useState(true);

  React.useEffect(() => {
    try {
      window.parent?.postMessage({ type: "kmv:ready", publicId }, "*");
    } catch {
      /* ignored */
    }
    function onMessage(event: MessageEvent) {
      const data = event.data as { type?: string } | null;
      if (!data?.type) return;
      if (data.type === "kmv:open") setOpen(true);
      if (data.type === "kmv:close") setOpen(false);
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  if (!open) return null;

  return (
    <div className="flex h-full w-full items-stretch justify-stretch">
      <PublicChatWindow
        publicId={publicId}
        layout="embed"
        onClose={() => {
          setOpen(false);
          try {
            window.parent?.postMessage({ type: "kmv:close" }, "*");
          } catch {
            /* ignored */
          }
        }}
      />
    </div>
  );
}
