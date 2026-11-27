"use client";
import * as React from "react";
import {
  MoreHorizontal,
  Eye,
  RefreshCw,
  Trash2,
  FileText,
  Link2,
  Globe,
  MessageSquareText,
  Upload,
  AlertTriangle,
  EyeOff,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SourceStatusBadge } from "./status-badge";
import { ERROR_CODE_COPY, type DocumentRow } from "@/lib/types";
import { fromNow, formatBytes, cn } from "@/lib/utils";

const TYPE_ICONS: Record<DocumentRow["type"], React.ElementType> = {
  file: Upload,
  text: FileText,
  faq: MessageSquareText,
  url: Link2,
  crawl_page: Globe,
};

const TYPE_LABELS: Record<DocumentRow["type"], string> = {
  file: "File",
  text: "Text",
  faq: "FAQ",
  url: "URL",
  crawl_page: "Crawl page",
};

type Props = {
  row: DocumentRow;
  onOpen: (row: DocumentRow) => void;
  onRefresh: (row: DocumentRow) => void;
  onDelete: (row: DocumentRow) => void;
  onToggleDisabled: (row: DocumentRow) => void;
};

export function SourceRow({ row, onOpen, onRefresh, onDelete, onToggleDisabled }: Props) {
  const TypeIcon = TYPE_ICONS[row.type];
  const canRefresh = row.status === "failed" || row.status === "ready";
  const isDisabled = Boolean(row.disabled_at);
  const errorMessage =
    row.status === "failed" && row.error_code
      ? ERROR_CODE_COPY[row.error_code] || `Failed: ${row.error_code}`
      : null;

  return (
    <li
      className={cn(
        "group grid grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-border px-5 py-4 text-sm last:border-b-0 hover:bg-subtle/40",
        isDisabled && "opacity-60"
      )}
    >
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
        <TypeIcon aria-hidden className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onOpen(row)}
            className="truncate text-left font-medium text-foreground hover:text-primary"
          >
            {row.title}
          </button>
          <SourceStatusBadge status={row.status} stage={row.stage} />
          {isDisabled && (
            <Badge tone="neutral">
              <EyeOff className="h-3 w-3" /> Disabled
            </Badge>
          )}
          {row.tags.map((tag) => (
            <Badge key={tag} tone="primary">
              {tag}
            </Badge>
          ))}
        </div>
        <div className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
          <span>{TYPE_LABELS[row.type]}</span>
          <span aria-hidden>·</span>
          <span>Added {fromNow(row.created_at)}</span>
          {row.size_bytes ? (
            <>
              <span aria-hidden>·</span>
              <span>{formatBytes(row.size_bytes)}</span>
            </>
          ) : null}
          {row.chunk_count ? (
            <>
              <span aria-hidden>·</span>
              <span>{row.chunk_count} chunks</span>
            </>
          ) : null}
        </div>
        {errorMessage && (
          <p className="mt-2 flex items-start gap-1 rounded-md bg-destructive/10 px-2 py-1 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            <span>{errorMessage}</span>
          </p>
        )}
      </div>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" onClick={() => onOpen(row)}>
          <Eye className="h-4 w-4" /> View
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="More actions">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={() => onRefresh(row)}
              disabled={!canRefresh}
            >
              <RefreshCw className="h-4 w-4" />
              Refresh / re-index
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => onToggleDisabled(row)}>
              <EyeOff className="h-4 w-4" />
              {isDisabled ? "Enable source" : "Disable source"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => onDelete(row)}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="h-4 w-4" />
              Delete source
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </li>
  );
}
