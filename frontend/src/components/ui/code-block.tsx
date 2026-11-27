"use client";
import * as React from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface CodeBlockProps {
  code: string;
  language?: string;
  className?: string;
}

/** Install snippets (D7.2) and the playground's raw trace view (D7.5).
 * No syntax highlighter -- these are short, copy-to-use snippets, not a
 * code editor; add one later if a page actually needs token coloring. */
export function CodeBlock({ code, language, className }: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={cn("group relative overflow-hidden rounded-lg border border-border bg-[hsl(var(--foreground)/0.04)]", className)}>
      {language && (
        <div className="flex items-center justify-between border-b border-border px-3 py-1.5 text-xs text-muted-foreground">
          <span className="font-mono">{language}</span>
        </div>
      )}
      <Button
        variant="ghost"
        size="icon"
        onClick={copy}
        aria-label="Copy code"
        className={cn("absolute right-2 top-2 h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100", !language && "top-2")}
      >
        {copied ? <Check className="h-4 w-4 text-success" /> : <Copy className="h-4 w-4" />}
      </Button>
      <pre className="overflow-x-auto p-4 pr-12 text-sm">
        <code className="font-mono text-foreground">{code}</code>
      </pre>
    </div>
  );
}
