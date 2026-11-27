"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LogOut,
  Settings,
  User,
  ChevronDown,
  Menu,
  Search,
  Bell,
  CheckCircle2,
  ShieldAlert,
  Keyboard,
  Mail,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar } from "@/components/ui/avatar";
import { Kbd, modKey } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { describeError } from "@/lib/errors";
import { cn } from "@/lib/utils";

type MeResponse = {
  id: string;
  email: string;
  name: string | null;
  avatar_key: string | null;
  email_verified_at: string | null;
};

/**
 * Premium top bar. Brings three things the earlier version lacked:
 *   - Breadcrumbs that keep users oriented inside nested pages.
 *   - A command-bar pill with the ⌘K hint (opens a lightweight palette).
 *   - A notification bell with a pulse when something is new.
 */
export function TopBar({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { toast } = useToast();
  const [me, setMe] = React.useState<MeResponse | null>(null);
  const [cmdOpen, setCmdOpen] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await apiFetch<MeResponse>("/api/bff/me");
        if (!cancelled) setMe(data);
      } catch {
        /* session may have expired; the middleware will catch the next nav */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ⌘K opens the command bar.
  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen(true);
      } else if (e.key === "Escape") {
        setCmdOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function signOut() {
    try {
      await apiFetch("/api/bff/auth/logout", { method: "POST" });
      router.replace("/login");
      router.refresh();
    } catch (error) {
      const info = describeError(error);
      toast({ tone: "danger", title: info.title, description: info.message });
    }
  }

  const crumbs = buildCrumbs(pathname, title);
  const unverified = me && !me.email_verified_at;

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-border bg-background/75 backdrop-blur-xl">
        <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
            aria-label="Open menu"
            onClick={() => router.push("/overview")}
          >
            <Menu className="h-4 w-4" />
          </button>

          <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
            <ol className="flex items-center gap-1.5 text-sm">
              {crumbs.map((c, i) => (
                <li key={`${c.href}-${i}`} className="flex items-center gap-1.5">
                  {i > 0 && (
                    <span className="text-muted-foreground/50" aria-hidden>
                      /
                    </span>
                  )}
                  {i === crumbs.length - 1 ? (
                    <span className="truncate font-display text-lg font-semibold tracking-tight">
                      {c.label}
                    </span>
                  ) : (
                    <Link
                      href={c.href}
                      className="truncate text-muted-foreground hover:text-foreground"
                    >
                      {c.label}
                    </Link>
                  )}
                </li>
              ))}
            </ol>
            {description && (
              <p className="truncate text-xs text-muted-foreground">{description}</p>
            )}
          </nav>

          {actions && <div className="hidden items-center gap-2 sm:flex">{actions}</div>}

          <button
            type="button"
            onClick={() => setCmdOpen(true)}
            className="group hidden items-center gap-2 rounded-lg border border-border bg-subtle/60 px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-muted-foreground/30 hover:bg-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:inline-flex"
          >
            <Search className="h-4 w-4" aria-hidden />
            <span className="w-36 text-left">Search…</span>
            <Kbd>{modKey()}K</Kbd>
          </button>

          <Tooltip content="No new alerts">
            <button
              type="button"
              aria-label="Notifications"
              className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground transition-colors hover:text-foreground"
            >
              <Bell className="h-4 w-4" />
            </button>
          </Tooltip>

          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label="Open account menu"
              className={cn(
                "inline-flex items-center gap-2 rounded-lg border border-border bg-card px-1.5 py-1 text-sm input-elevated transition-colors hover:bg-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              )}
            >
              <Avatar size="sm" name={me?.name} email={me?.email} />
              <span className="hidden min-w-0 flex-col items-start pr-1 leading-tight sm:flex">
                <span className="max-w-[12rem] truncate text-sm font-medium">
                  {me?.name || me?.email?.split("@")[0] || "Loading…"}
                </span>
                <span className="max-w-[12rem] truncate text-[11px] text-muted-foreground">
                  {me?.email ?? ""}
                </span>
              </span>
              <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <div className="flex items-center gap-2.5 px-2 py-2">
                <Avatar size="md" name={me?.name} email={me?.email} />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {me?.name || me?.email || "Account"}
                  </p>
                  {me?.email && (
                    <p className="truncate text-xs text-muted-foreground">{me.email}</p>
                  )}
                </div>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/settings">
                  <User className="h-4 w-4" />
                  Profile &amp; preferences
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/settings">
                  <Settings className="h-4 w-4" />
                  Workspace settings
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setCmdOpen(true)}>
                <Keyboard className="h-4 w-4" />
                <span className="flex-1">Command bar</span>
                <Kbd>{modKey()}K</Kbd>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={signOut}
                className="text-destructive focus:text-destructive"
              >
                <LogOut className="h-4 w-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {unverified && (
          <div className="border-t border-warning/30 bg-warning/10">
            <div className="flex items-center justify-between gap-3 px-4 py-2 text-xs text-warning sm:px-6 lg:px-8">
              <span className="inline-flex items-center gap-2">
                <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
                Your email isn&apos;t verified. Some owner actions are limited until you verify.
              </span>
              <Link
                href={`/verify-email?email=${encodeURIComponent(me!.email)}`}
                className="inline-flex items-center gap-1 font-medium underline-offset-4 hover:underline"
              >
                <Mail className="h-3 w-3" />
                Resend verification
              </Link>
            </div>
          </div>
        )}
      </header>

      {cmdOpen && <CommandBar onClose={() => setCmdOpen(false)} />}
    </>
  );
}

// --- Breadcrumbs ----------------------------------------------------------

const CRUMB_LABELS: Record<string, string> = {
  overview: "Overview",
  onboarding: "Onboarding",
  knowledge: "Knowledge",
  chatbot: "Chatbot",
  publish: "Publish",
  conversations: "Conversations",
  usage: "Usage",
  settings: "Settings",
};

function buildCrumbs(pathname: string, title: string): Array<{ href: string; label: string }> {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return [{ href: "/overview", label: title }];
  const crumbs: Array<{ href: string; label: string }> = [];
  let cursor = "";
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    cursor += "/" + seg;
    if (i === segments.length - 1) {
      crumbs.push({ href: cursor, label: title });
    } else {
      crumbs.push({ href: cursor, label: CRUMB_LABELS[seg] ?? seg });
    }
  }
  return crumbs;
}

// --- Command bar ----------------------------------------------------------

const QUICK_ACTIONS = [
  { label: "Go to Overview", href: "/overview", shortcut: "O" },
  { label: "Add a knowledge source", href: "/knowledge", shortcut: "K" },
  { label: "Shape the chatbot", href: "/chatbot", shortcut: "B" },
  { label: "Publish snapshot", href: "/chatbot/publish" },
  { label: "View conversations", href: "/conversations", shortcut: "C" },
  { label: "Usage &amp; limits", href: "/usage", shortcut: "U" },
  { label: "Open settings", href: "/settings", shortcut: "," },
];

function CommandBar({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = React.useState("");
  const [active, setActive] = React.useState(0);

  const items = React.useMemo(() => {
    if (!q.trim()) return QUICK_ACTIONS;
    const needle = q.toLowerCase();
    return QUICK_ACTIONS.filter((a) => a.label.toLowerCase().includes(needle));
  }, [q]);

  React.useEffect(() => setActive(0), [q]);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const picked = items[active];
      if (picked) {
        router.push(picked.href);
        onClose();
      }
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command bar"
      className="fixed inset-0 z-[80] flex items-start justify-center bg-background/60 px-4 pt-[16vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-card shadow-elevated animate-fade-in"
      >
        <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
          <Search className="h-4 w-4 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Jump to…"
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
            aria-label="Search actions"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul role="listbox" className="max-h-80 overflow-y-auto p-1.5">
          {items.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">No matches.</li>
          ) : (
            items.map((item, i) => (
              <li key={item.href}>
                <button
                  type="button"
                  role="option"
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => {
                    router.push(item.href);
                    onClose();
                  }}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                    i === active ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                  )}
                >
                  <CheckCircle2
                    aria-hidden
                    className={cn(
                      "h-3.5 w-3.5",
                      i === active ? "text-primary" : "text-transparent"
                    )}
                  />
                  <span
                    className="flex-1 text-left"
                    dangerouslySetInnerHTML={{ __html: item.label }}
                  />
                  {item.shortcut && <Kbd>{item.shortcut}</Kbd>}
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center justify-between gap-2 border-t border-border bg-subtle/60 px-3 py-2 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            to navigate
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>Enter</Kbd>
            to open
          </span>
        </div>
      </div>
    </div>
  );
}
