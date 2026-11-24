"use client";
import * as React from "react";
import { Alert } from "@/components/ui/alert";
import { describeError } from "@/lib/errors";

export function FormErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  const info = describeError(error);
  return (
    <Alert tone="danger" title={info.title}>
      <div className="space-y-1">
        <p>{info.message}</p>
        {info.requestId && (
          <p className="text-[11px] opacity-80">
            Reference: <code className="font-mono">{info.requestId}</code>
          </p>
        )}
      </div>
    </Alert>
  );
}
