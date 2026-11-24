import Link from "next/link";
import { ArrowRight, Sparkles, ShieldCheck, Zap, MessageSquareText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/ui/icon-logo";

export default function HomePage() {
  return (
    <main className="relative min-h-screen bg-background text-foreground">
      <div aria-hidden className="pointer-events-none absolute inset-0 hero-grid opacity-70" />
      <header className="relative">
        <nav className="container flex items-center justify-between py-6">
          <Link href="/" aria-label="Knowmivo home" className="flex items-center gap-2">
            <Logo withWordmark />
          </Link>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/signup">
                Get started
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </nav>
      </header>

      <section className="relative">
        <div className="container grid gap-12 pb-24 pt-10 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:pt-24">
          <div className="space-y-8">
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-accent px-3 py-1 text-xs font-medium text-accent-foreground">
              <Sparkles aria-hidden className="h-3.5 w-3.5" />
              Your knowledge. Ready to answer.
            </span>
            <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
              An assistant that{" "}
              <span className="relative inline-block">
                <span className="bg-gradient-to-br from-primary to-[hsl(260_100%_60%)] bg-clip-text text-transparent">
                  only ever answers
                </span>
                <span
                  aria-hidden
                  className="absolute inset-x-0 -bottom-1 h-2 rounded-full bg-primary/15 blur-sm"
                />
              </span>{" "}
              from your sources.
            </h1>
            <p className="max-w-xl text-lg leading-relaxed text-muted-foreground">
              Upload your docs. Paste FAQs. Point us at your site. Publish a chat widget that cites
              the exact paragraph on every reply — grounded, fast and embeddable anywhere.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link href="/signup">
                  Start free
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="secondary" size="lg">
                <Link href="/login">I already have an account</Link>
              </Button>
            </div>
            <dl className="grid max-w-md grid-cols-3 gap-6 border-t border-border pt-6 text-sm">
              {[
                { label: "Sources cited", value: "100%" },
                { label: "Setup", value: "~5 min" },
                { label: "Languages", value: "EN + BN" },
              ].map((item) => (
                <div key={item.label}>
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">{item.label}</dt>
                  <dd className="font-display text-lg font-semibold">{item.value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="relative">
            <div
              aria-hidden
              className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-primary/10 via-transparent to-[hsl(260_100%_60%/0.1)] blur-2xl"
            />
            <div className="relative overflow-hidden rounded-2xl border border-border bg-card shadow-elevated">
              <div className="flex items-center justify-between border-b border-border bg-subtle px-4 py-3">
                <div className="flex items-center gap-2">
                  <Logo />
                  <div>
                    <p className="text-sm font-medium text-foreground">Acme Support</p>
                    <p className="text-xs text-muted-foreground">Online · replies grounded in 42 sources</p>
                  </div>
                </div>
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" aria-hidden />
                  Live
                </span>
              </div>
              <div className="space-y-4 p-5 text-sm">
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2.5 text-primary-foreground shadow-sm">
                    What&rsquo;s your return policy for international orders?
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[88%] space-y-2 rounded-2xl rounded-bl-sm border border-border bg-subtle px-3.5 py-2.5 text-foreground">
                    <p>
                      International returns are accepted within 30 days of delivery. Shipping is covered
                      for defective items, and otherwise paid by the customer <sup className="text-primary">[1]</sup>.
                    </p>
                    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">[1]</span> Returns &amp; Refunds Policy · page 2
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
                  <span className="inline-flex h-1.5 w-1.5 animate-pulse rounded-full bg-primary" aria-hidden />
                  Assistant is typing…
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="relative border-t border-border bg-subtle/60">
        <div className="container grid gap-6 py-16 sm:grid-cols-2 lg:grid-cols-3">
          {[
            {
              icon: ShieldCheck,
              title: "Grounded answers only",
              body:
                "Every reply cites the source and page. If your docs don't cover it, the bot says so instead of inventing an answer.",
            },
            {
              icon: Zap,
              title: "Live in minutes",
              body:
                "Upload a PDF or paste your site URL. We parse, chunk and index — you publish a widget to your site.",
            },
            {
              icon: MessageSquareText,
              title: "Embed anywhere",
              body:
                "One script tag. React and Next.js snippets. A hosted chat page. Same assistant across every surface.",
            },
          ].map((feature) => (
            <div key={feature.title} className="card-surface p-6">
              <feature.icon aria-hidden className="h-6 w-6 text-primary" />
              <h3 className="mt-4 font-display text-lg font-semibold">{feature.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{feature.body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="container flex flex-col items-center justify-between gap-4 py-10 sm:flex-row">
          <div className="flex items-center gap-2">
            <Logo />
            <span className="text-sm text-muted-foreground">© {new Date().getFullYear()} Knowmivo</span>
          </div>
          <div className="flex gap-6 text-sm text-muted-foreground">
            <Link href="/login" className="hover:text-foreground">
              Sign in
            </Link>
            <Link href="/signup" className="hover:text-foreground">
              Sign up
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
