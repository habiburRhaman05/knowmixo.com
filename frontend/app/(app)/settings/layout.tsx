"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings", label: "Account" },
  { href: "/settings/security", label: "Security" },
  { href: "/settings/team", label: "Team" },
  { href: "/settings/escalation", label: "Escalation" },
  { href: "/settings/api-keys", label: "API keys" },
  { href: "/settings/billing", label: "Billing" },
  { href: "/settings/integrations", label: "Integrations" },
];

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <>
      <TopBar title="Settings" description="Account, team, security and integrations." />
      <main>
        <PageShell>
          <nav aria-label="Settings sections" className="mb-6 flex flex-wrap gap-1 border-b border-border">
            {TABS.map((tab) => {
              const active = pathname === tab.href;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
                    active
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  )}
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
          {children}
        </PageShell>
      </main>
    </>
  );
}
