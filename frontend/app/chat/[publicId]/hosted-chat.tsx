"use client";
import { PublicChatWindow } from "@/components/chat/public-chat-window";

/**
 * Standalone (non-embedded) hosted chat page. Same `PublicChatWindow`
 * component as the iframe widget, just wrapped in a centered layout
 * instead of a floating bubble.
 */
export function HostedChat({ publicId }: { publicId: string }) {
  return (
    <div className="relative mx-auto flex h-[calc(100vh-96px)] w-full flex-col overflow-hidden">
      <PublicChatWindow publicId={publicId} layout="hosted" />
    </div>
  );
}
