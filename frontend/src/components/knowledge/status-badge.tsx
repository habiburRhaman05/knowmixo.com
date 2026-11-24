import * as React from "react";
import { Check, Circle, Loader2, Pause, AlertTriangle, Archive } from "lucide-react";
import { STATUS_META, type DocumentStatus, type DocumentStage, STAGE_LABEL } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICONS: Record<
  DocumentStatus,
  { Icon: React.ElementType; spin?: boolean }
> = {
  pending: { Icon: Circle },
  processing: { Icon: Loader2, spin: true },
  retrying: { Icon: Loader2, spin: true },
  quota_wait: { Icon: Pause },
  ready: { Icon: Check },
  failed: { Icon: AlertTriangle },
  retired: { Icon: Archive },
};

const TONE_CLASS = {
  ready: "status-ready",
  processing: "status-processing",
  waiting: "status-waiting",
  failed: "status-failed",
  idle: "status-idle",
} as const;

export function SourceStatusBadge({
  status,
  stage,
  className,
}: {
  status: DocumentStatus | null;
  stage?: DocumentStage;
  className?: string;
}) {
  const key = (status ?? "pending") as DocumentStatus;
  const meta = STATUS_META[key] ?? STATUS_META.pending;
  const { Icon, spin } = ICONS[key] ?? ICONS.pending;
  const stageSuffix =
    (key === "processing" || key === "retrying") && stage && STAGE_LABEL[stage]
      ? ` · ${STAGE_LABEL[stage]}`
      : "";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE_CLASS[meta.tone],
        className
      )}
    >
      <Icon aria-hidden className={cn("h-3 w-3", spin && "animate-spin")} />
      {meta.label}
      {stageSuffix}
    </span>
  );
}
