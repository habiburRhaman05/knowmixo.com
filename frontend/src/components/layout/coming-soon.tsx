import * as React from "react";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/**
 * Lightweight placeholder used for the sidebar entries that F1 reserves
 * space for but doesn't own (Knowledge / Chatbot / Conversations / Settings
 * land in F2, F3, F5, F5). Never shows a dead link.
 */
export function ComingSoon({
  title,
  description,
  points,
  sprint,
}: {
  title: string;
  description: string;
  points: string[];
  sprint: string;
}) {
  return (
    <Card>
      <CardHeader className="space-y-3">
        <Badge tone="primary" className="w-fit">
          <Sparkles aria-hidden className="h-3 w-3" />
          Coming in {sprint}
        </Badge>
        <CardTitle className="text-xl">{title}</CardTitle>
        <CardDescription className="max-w-prose text-base leading-relaxed">
          {description}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ul className="grid gap-2 sm:grid-cols-2">
          {points.map((p) => (
            <li
              key={p}
              className="flex items-start gap-2 rounded-lg border border-dashed border-border bg-subtle/60 p-3 text-sm text-muted-foreground"
            >
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
              <span>{p}</span>
            </li>
          ))}
        </ul>
        <Button asChild variant="secondary">
          <Link href="/overview">
            Back to overview
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
