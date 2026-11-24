import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertCircle, CheckCircle2, Info, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-lg border p-4 text-sm leading-relaxed [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg+div]:translate-y-0 [&:has(svg)]:pl-11",
  {
    variants: {
      tone: {
        info: "border-primary/20 bg-accent/60 text-accent-foreground",
        success: "border-success/30 bg-success/10 text-success",
        warning: "border-warning/30 bg-warning/10 text-warning",
        danger: "border-destructive/30 bg-destructive/10 text-destructive",
      },
    },
    defaultVariants: { tone: "info" },
  }
);

const ICONS: Record<NonNullable<VariantProps<typeof alertVariants>["tone"]>, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertCircle,
  danger: AlertCircle,
};

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  title?: string;
  icon?: LucideIcon | null;
}

export function Alert({ className, tone, title, icon, children, ...props }: AlertProps) {
  const Icon = icon ?? ICONS[tone ?? "info"];
  return (
    <div role="alert" className={cn(alertVariants({ tone, className }))} {...props}>
      {Icon && <Icon aria-hidden className="h-4 w-4" />}
      <div>
        {title && <p className="mb-1 font-medium">{title}</p>}
        <div className="text-[13px] leading-5">{children}</div>
      </div>
    </div>
  );
}
