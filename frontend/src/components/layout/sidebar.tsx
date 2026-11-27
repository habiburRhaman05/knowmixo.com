"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  Bot,
  MessageSquare,
  Inbox,
  Gauge,
  Settings,
  Lightbulb,
  FlaskConical,
  Webhook,
  ChevronsUpDown,
  Sparkles,
  Rocket,
  ExternalLink,
  type LucideIcon,
} from "lucide-react";
import { Logo } from "@/components/ui/icon-logo";
import { Avatar, initialsFor } from "@/components/ui/avatar";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { useCompany } from "@/lib/hooks/use-company";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon; shortcut?: string };

const SECTIONS: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Overview",
    items: [
      { href: "/overview", label: "Overview", icon: LayoutDashboard, shortcut: "O" },
      { href: "/onboarding", label: "Onboarding", icon: Rocket, shortcut: "N" },
    ],
  },
  {
    title: "Build",
    items: [
      { href: "/knowledge", label: "Knowledge", icon: BookOpen, shortcut: "K" },
      { href: "/chatbot", label: "Chatbot", icon: Bot, shortcut: "B" },
      { href: "/playground", label: "Playground", icon: FlaskConical, shortcut: "P" },
      { href: "/actions", label: "Actions", icon: Webhook, shortcut: "A" },
    ],
  },
  {
    title: "Operate",
    items: [
      { href: "/inbox", label: "Inbox", icon: Inbox, shortcut: "I" },
      { href: "/conversations", label: "Conversations", icon: MessageSquare, shortcut: "C" },
      { href: "/quality", label: "Quality", icon: Lightbulb, shortcut: "Q" },
      { href: "/usage", label: "Usage", icon: Gauge, shortcut: "U" },
      { href: "/settings", label: "Settings", icon: Settings, shortcut: "," },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: company } = useCompany();

  return (
    <aside className="hidden h-screen w-64 shrink-0 border-r border-border bg-card md:sticky md:top-0 md:flex md:flex-col">
      <div className="flex items-center gap-2 px-5 pb-3 pt-6">
        <Link href="/overview" aria-label="Knowmivo dashboard" className="flex items-center gap-2">
          <Logo withWordmark />
        </Link>
      </div>

      <div className="px-3">
        <Tooltip content="Workspace switcher — only one company in V1" side="right">
          <button
            type="button"
            className="group flex w-full items-center gap-2.5 rounded-lg border border-border bg-subtle/60 px-2.5 py-2 text-left text-sm transition-colors hover:bg-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Avatar
              size="sm"
              name={company?.name ?? "Your workspace"}
              className="shrink-0"
            />
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate font-medium text-foreground">
                {company?.name || "Your workspace"}
              </span>
              <span className="block text-[11px] text-muted-foreground">Free beta</span>
            </span>
            <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground opacity-60 group-hover:opacity-100" />
          </button>
        </Tooltip>
      </div>

      <nav aria-label="Primary" className="mt-4 flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
              {section.title}
            </p>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "group relative flex items-center gap-3 rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors",
                        active
                          ? "bg-accent text-accent-foreground"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      )}
                    >
                      {active && (
                        <span
                          aria-hidden
                          className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-primary"
                        />
                      )}
                      <Icon
                        aria-hidden
                        className={cn(
                          "h-4 w-4",
                          active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                        )}
                      />
                      <span className="flex-1">{item.label}</span>
                      {item.shortcut && (
                        <Kbd className="opacity-0 group-hover:opacity-100">{item.shortcut}</Kbd>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <Link
          href="https://knowmivo.com/docs"
          target="_blank"
          rel="noreferrer"
          className="group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-primary/80 to-[hsl(260_100%_60%)] text-primary-foreground">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <span className="flex-1 leading-tight">
            <span className="block font-medium text-foreground">Docs &amp; API</span>
            <span className="block text-[11px]">Learn how to embed anywhere</span>
          </span>
          <ExternalLink className="h-3 w-3 opacity-60 group-hover:opacity-100" />
        </Link>
        <div className="mt-2 flex items-center justify-between px-2.5 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="dot-pulse inline-block h-1.5 w-1.5 rounded-full bg-success text-success"
              aria-hidden
            />
            All systems normal
          </span>
          <span>v1.0</span>
        </div>
      </div>
    </aside>
  );
}
