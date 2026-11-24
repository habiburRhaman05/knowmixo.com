import * as React from "react";
import Link from "next/link";
import { ShieldCheck, Sparkles, Zap, Quote } from "lucide-react";
import { Logo } from "@/components/ui/icon-logo";
import { Separator } from "@/components/ui/separator";

/**
 * Premium two-panel auth layout. Left panel is a dark gradient hero with
 * a grain overlay, live-status pill, feature list, pull quote and a
 * SOC-ready trust row. Right panel is the form card. On <lg widths the
 * hero collapses to a thin branded header so the form owns the fold.
 */
export function AuthShell({
  children,
  title,
  description,
  footer,
}: {
  children: React.ReactNode;
  title: string;
  description: string;
  footer?: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen bg-background">
      <div className="pointer-events-none absolute inset-0 hero-grid opacity-70" aria-hidden />
      <div className="relative grid min-h-screen grid-cols-1 lg:grid-cols-[1.1fr_1fr]">
        <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-border bg-[hsl(224_28%_8%)] text-white lg:flex grain">
          <div
            className="absolute inset-0 opacity-70"
            aria-hidden
            style={{
              background:
                "radial-gradient(circle at 20% 10%, hsla(243,85%,65%,0.35), transparent 55%)," +
                "radial-gradient(circle at 80% 30%, hsla(260,90%,65%,0.3), transparent 55%)," +
                "radial-gradient(circle at 50% 100%, hsla(222,90%,55%,0.2), transparent 55%)",
            }}
          />
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.12]"
            aria-hidden
            style={{
              backgroundImage:
                "linear-gradient(rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.4) 1px, transparent 1px)",
              backgroundSize: "44px 44px",
              maskImage: "radial-gradient(ellipse at center, black 40%, transparent 80%)",
            }}
          />

          <div className="relative flex items-center justify-between p-10">
            <Link href="/" className="flex items-center gap-2" aria-label="Knowmivo home">
              <Logo withWordmark className="[&_span:last-child]:text-white" />
            </Link>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] font-medium text-white/70 backdrop-blur">
              <span
                className="dot-pulse inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 text-emerald-400"
                aria-hidden
              />
              All systems operational
            </span>
          </div>

          <div className="relative flex-1 px-10">
            <div className="max-w-md space-y-7">
              <div className="space-y-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-white/50">
                  Your knowledge. Ready to answer.
                </p>
                <h2 className="font-display text-[2.1rem] font-semibold leading-[1.1] tracking-tight">
                  Launch a grounded assistant your customers actually trust.
                </h2>
                <p className="text-sm leading-relaxed text-white/60">
                  Point us at your docs, FAQs and website. Publish a widget that cites every answer
                  back to the exact paragraph it came from.
                </p>
              </div>

              <ul className="space-y-3 text-sm text-white/80">
                {[
                  { Icon: Sparkles, label: "Answers cite the exact source and page" },
                  { Icon: ShieldCheck, label: "Your data stays yours — never used to train models" },
                  { Icon: Zap, label: "Embed on your site in a single script tag" },
                ].map(({ Icon, label }) => (
                  <li key={label} className="flex items-start gap-3">
                    <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/10 text-white/90 ring-1 ring-inset ring-white/10">
                      <Icon className="h-3.5 w-3.5" aria-hidden />
                    </span>
                    <span>{label}</span>
                  </li>
                ))}
              </ul>

              <figure className="relative rounded-2xl border border-white/10 bg-white/[0.04] p-5 text-sm leading-relaxed text-white/75 backdrop-blur">
                <Quote
                  aria-hidden
                  className="absolute -left-2 -top-2 h-5 w-5 text-white/40"
                />
                <blockquote>
                  &ldquo;We went from a six-tab help center to one search bar that quotes the exact
                  paragraph every time. Our ticket volume dropped the first week.&rdquo;
                </blockquote>
                <figcaption className="mt-3 flex items-center gap-2 text-xs text-white/50">
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-fuchsia-400 to-amber-300 text-[10px] font-semibold text-slate-900">
                    SR
                  </span>
                  <span>
                    <span className="block font-medium text-white/80">Sam Rao</span>
                    Head of Support, SaaS product
                  </span>
                </figcaption>
              </figure>
            </div>
          </div>

          <div className="relative px-10 pb-10 pt-8">
            <div className="mb-5 h-px w-full bg-gradient-to-r from-transparent via-white/15 to-transparent" />
            <div className="flex items-center justify-between text-xs text-white/50">
              <div className="flex items-center gap-4">
                {["Grounded", "Cited", "Private", "Free beta"].map((w) => (
                  <span key={w} className="uppercase tracking-[0.18em]">
                    {w}
                  </span>
                ))}
              </div>
              <span>© {new Date().getFullYear()} Knowmivo</span>
            </div>
          </div>
        </aside>

        <main className="relative flex flex-col px-4 py-6 sm:px-10 lg:justify-center lg:px-16 lg:py-10">
          <div className="lg:hidden pb-5">
            <Link href="/" aria-label="Knowmivo home" className="flex items-center gap-2">
              <Logo withWordmark />
            </Link>
          </div>
          <div className="mx-auto w-full max-w-md">
            <div className="mb-8 space-y-2 animate-fade-in">
              <h1 className="font-display text-[1.7rem] font-semibold leading-tight tracking-tight sm:text-3xl">
                {title}
              </h1>
              <p className="text-sm text-muted-foreground">{description}</p>
            </div>
            <div className="animate-fade-in" style={{ animationDelay: "40ms" }}>
              {children}
            </div>
            {footer && (
              <div className="animate-fade-in" style={{ animationDelay: "80ms" }}>
                <Separator className="my-8" />
                <div className="text-sm text-muted-foreground">{footer}</div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
