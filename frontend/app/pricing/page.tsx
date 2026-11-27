import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/ui/icon-logo";
import { PricingGrid } from "./pricing-grid";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Simple, usage-based pricing for Knowmivo — from a free tier to agency-scale plans.",
};

const FAQS = [
  {
    q: "What counts as an AI reply?",
    a: "Each message your assistant sends back to a visitor counts once. Messages the assistant doesn't need to answer with AI (like a human taking over in the inbox) don't count.",
  },
  {
    q: "What happens if I go over my plan's limit?",
    a: "We'll let you know before you hit the wall. You can upgrade any time, and your assistant keeps answering — it never just stops without warning.",
  },
  {
    q: "Can I switch plans later?",
    a: "Yes. Upgrade or downgrade any time from Settings → Billing. Changes take effect immediately and billing is prorated.",
  },
  {
    q: "Do you offer a free trial on paid plans?",
    a: "Yes — start any paid plan and you won't be charged until the trial ends. Cancel any time before then from the billing portal.",
  },
];

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="container flex h-16 items-center justify-between">
          <Link href="/" aria-label="Knowmivo home" className="flex items-center gap-2">
            <Logo withWordmark />
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            <Link href="/pricing" className="font-medium text-foreground">
              Pricing
            </Link>
            <Link href="/login" className="text-muted-foreground hover:text-foreground">
              Sign in
            </Link>
            <Button asChild size="sm">
              <Link href="/signup">
                Get started
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </nav>
        </div>
      </header>

      <section className="container py-16 text-center">
        <h1 className="font-display text-4xl font-semibold tracking-tight sm:text-5xl">
          Simple pricing that grows with you
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
          Start free. Upgrade when your assistant starts carrying real conversation volume. No
          surprises — every plan shows exactly what's included below.
        </p>
      </section>

      <section className="container pb-20">
        <PricingGrid />
      </section>

      <section className="border-t border-border bg-subtle/60">
        <div className="container max-w-3xl py-16">
          <h2 className="font-display text-2xl font-semibold">Frequently asked questions</h2>
          <dl className="mt-8 space-y-6">
            {FAQS.map((item) => (
              <div key={item.q}>
                <dt className="font-medium">{item.q}</dt>
                <dd className="mt-1 text-sm leading-relaxed text-muted-foreground">{item.a}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="container flex flex-col items-center justify-between gap-4 py-10 sm:flex-row">
          <div className="flex items-center gap-2">
            <Logo />
            <span className="text-sm text-muted-foreground">© {new Date().getFullYear()} Knowmivo</span>
          </div>
          <div className="flex gap-6 text-sm text-muted-foreground">
            <Link href="/privacy" className="hover:text-foreground">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-foreground">
              Terms
            </Link>
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
