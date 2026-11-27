import type { Metadata, Viewport } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
import * as React from "react";
import "./globals.css";
import { ToastProvider } from "@/components/ui/toast";
import { CookieConsent } from "@/components/layout/cookie-consent";
import { QueryProvider } from "@/components/providers/query-provider";
import { publicEnv } from "@/lib/env";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const display = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(publicEnv.appUrl),
  title: {
    default: "Knowmivo — Your knowledge. Ready to answer.",
    template: "%s · Knowmivo",
  },
  description:
    "Turn your documents and website content into an embeddable chat assistant that cites every answer.",
  openGraph: {
    title: "Knowmivo",
    description:
      "Turn your documents and website content into an embeddable chat assistant that cites every answer.",
    type: "website",
  },
  icons: {
    icon: "/favicon.svg",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0d14" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable}`} suppressHydrationWarning>
      <body className="min-h-screen bg-background antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground"
        >
          Skip to main content
        </a>
        <QueryProvider>
          <ToastProvider>
            <div id="main">{children}</div>
          </ToastProvider>
          <CookieConsent />
        </QueryProvider>
      </body>
    </html>
  );
}
