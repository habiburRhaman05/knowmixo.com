import type { Metadata } from "next";
import { HostedChat } from "./hosted-chat";

export const metadata: Metadata = {
  title: "Chat",
  robots: { index: false, follow: false },
};

type Props = { params: Promise<{ publicId: string }> };

export default async function HostedChatPage({ params }: Props) {
  const { publicId } = await params;
  return (
    <div className="relative min-h-screen bg-background">
      <div aria-hidden className="pointer-events-none absolute inset-0 hero-grid opacity-70" />
      <main className="relative mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-8">
        <HostedChat publicId={publicId} />
      </main>
    </div>
  );
}
