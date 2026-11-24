"use client";
import * as React from "react";
import Link from "next/link";
import { ArrowRight, Building2, BookOpen, Palette, Eye, Rocket, Check } from "lucide-react";
import { TopBar } from "@/components/layout/topbar";
import { PageShell } from "@/components/layout/page-shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const STEPS = [
  {
    key: "company",
    icon: Building2,
    title: "Company details",
    body: "Name, website and industry. Used only inside your workspace.",
    href: "/settings",
    cta: "Edit company",
  },
  {
    key: "source",
    icon: BookOpen,
    title: "Add your first source",
    body: "Upload a doc, paste FAQs or let us crawl your site.",
    href: "/knowledge",
    cta: "Open Knowledge",
  },
  {
    key: "appearance",
    icon: Palette,
    title: "Shape the assistant",
    body: "Name, tone, color and greeting.",
    href: "/chatbot",
    cta: "Open studio",
  },
  {
    key: "preview",
    icon: Eye,
    title: "Preview the answers",
    body: "Chat with your draft before anyone else can.",
    href: "/chatbot",
    cta: "Open preview",
  },
  {
    key: "publish",
    icon: Rocket,
    title: "Publish the first snapshot",
    body: "Go live when you're happy with the preview.",
    href: "/chatbot",
    cta: "Publish",
  },
] as const;

export default function OnboardingPage() {
  return (
    <>
      <TopBar
        title="Onboarding"
        description="Get your assistant live in a few focused steps. You can return any time."
      />
      <main>
        <PageShell>
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Welcome — let&apos;s get you grounded</CardTitle>
                <CardDescription>
                  We saved your progress automatically. Each step opens the right place in the app.
                </CardDescription>
              </CardHeader>
            </Card>

            <ol className="relative space-y-4 border-l border-border pl-6">
              {STEPS.map((step, i) => (
                <li key={step.key} className="relative">
                  <span className="absolute -left-[33px] flex h-6 w-6 items-center justify-center rounded-full border border-border bg-background text-xs font-semibold text-muted-foreground">
                    {i + 1}
                  </span>
                  <Card>
                    <CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-start gap-4">
                        <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                          <step.icon aria-hidden className="h-5 w-5" />
                        </span>
                        <div className="space-y-1">
                          <p className="font-display text-base font-semibold">{step.title}</p>
                          <p className="text-sm text-muted-foreground">{step.body}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone="neutral">Not started</Badge>
                        <Button asChild size="sm" variant="secondary">
                          <Link href={step.href}>
                            {step.cta}
                            <ArrowRight className="h-4 w-4" />
                          </Link>
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ol>

            <Card>
              <CardContent className="flex items-center gap-3 py-5 text-sm">
                <Check aria-hidden className="h-5 w-5 text-success" />
                <p>
                  Nothing is published until you choose to. Every change is saved as a draft and only
                  the <strong className="font-medium">published snapshot</strong> is visible to visitors.
                </p>
              </CardContent>
            </Card>
          </div>
        </PageShell>
      </main>
    </>
  );
}
