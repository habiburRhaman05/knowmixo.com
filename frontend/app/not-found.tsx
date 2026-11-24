import Link from "next/link";
import { Compass, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/ui/icon-logo";

export default function NotFound() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-background px-4">
      <div aria-hidden className="pointer-events-none absolute inset-0 hero-grid opacity-70" />
      <div className="relative w-full max-w-md space-y-6 rounded-xl border border-border bg-card p-8 text-center shadow-elevated">
        <Logo withWordmark className="justify-center" />
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">404</p>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Page not found</h1>
          <p className="text-sm text-muted-foreground">
            The page you were looking for doesn&apos;t exist, or you don&apos;t have access.
          </p>
        </div>
        <div className="flex justify-center gap-2">
          <Button asChild>
            <Link href="/overview">
              <Home className="h-4 w-4" /> Go to overview
            </Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/">
              <Compass className="h-4 w-4" /> Home
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
