"use client";
import * as React from "react";
import Link from "next/link";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * Page-level error for the authenticated shell — keeps the sidebar and top
 * bar visible, so the user can still navigate out of a broken page.
 */
export default function AppSectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-12">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-destructive">
            <AlertTriangle aria-hidden className="h-4 w-4" />
            <CardTitle className="text-lg">This page hit an error</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>
            We couldn&apos;t load this screen. Retry below, or head back to the overview.
          </p>
          {error?.digest && (
            <p className="rounded-md bg-muted px-3 py-2 text-xs">
              Reference: <code className="font-mono">{error.digest}</code>
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={reset}>
              <RefreshCw className="h-4 w-4" /> Try again
            </Button>
            <Button asChild variant="secondary">
              <Link href="/overview">
                <Home className="h-4 w-4" /> Overview
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
