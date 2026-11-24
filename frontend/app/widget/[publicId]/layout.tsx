import type { Metadata } from "next";
import "@/../app/globals.css";
import { Inter } from "next/font/google";
import * as React from "react";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "Chat widget",
  robots: { index: false, follow: false },
};

/**
 * The widget is rendered inside an iframe on a third-party site. It MUST
 * stay out of the main site's layout — no Toast provider, no app chrome,
 * and the response doesn't send the X-Frame-Options: DENY header the rest
 * of the site uses. Framing is restricted by the backend's domain
 * allowlist on the session bootstrap call instead.
 */
export default function WidgetLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.variable}>
      <body
        className="h-screen w-screen overflow-hidden bg-transparent font-sans text-sm text-foreground antialiased"
      >
        {children}
      </body>
    </html>
  );
}
