"use client";
import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { X, CheckCircle2, AlertCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "info" | "success" | "danger" | "warning";

type ToastItem = {
  id: number;
  tone: Tone;
  title: string;
  description?: string;
};

type ToastCtx = {
  toast: (opts: Omit<ToastItem, "id"> | { tone?: Tone; title: string; description?: string }) => void;
};

const Ctx = React.createContext<ToastCtx | null>(null);

export function useToast() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

const ICONS: Record<Tone, React.ElementType> = {
  info: Info,
  success: CheckCircle2,
  danger: AlertCircle,
  warning: AlertCircle,
};

const TONE_CLASSES: Record<Tone, string> = {
  info: "border-primary/20 bg-card",
  success: "border-success/30 bg-card",
  danger: "border-destructive/30 bg-card",
  warning: "border-warning/30 bg-card",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const nextId = React.useRef(1);

  const toast = React.useCallback<ToastCtx["toast"]>((opts) => {
    const id = nextId.current++;
    const tone = (opts.tone ?? "info") as Tone;
    setItems((prev) => [...prev, { id, tone, title: opts.title, description: opts.description }]);
  }, []);

  return (
    <Ctx.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {items.map((item) => {
          const Icon = ICONS[item.tone];
          return (
            <ToastPrimitive.Root
              key={item.id}
              duration={5000}
              onOpenChange={(open) => {
                if (!open) setItems((prev) => prev.filter((i) => i.id !== item.id));
              }}
              className={cn(
                "pointer-events-auto grid gap-1 rounded-lg border p-4 pr-8 shadow-elevated data-[state=open]:animate-fade-in",
                TONE_CLASSES[item.tone]
              )}
            >
              <div className="flex items-start gap-2">
                <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="space-y-0.5">
                  <ToastPrimitive.Title className="text-sm font-medium leading-tight text-foreground">
                    {item.title}
                  </ToastPrimitive.Title>
                  {item.description && (
                    <ToastPrimitive.Description className="text-sm leading-snug text-muted-foreground">
                      {item.description}
                    </ToastPrimitive.Description>
                  )}
                </div>
              </div>
              <ToastPrimitive.Close
                aria-label="Dismiss notification"
                className="absolute right-2 top-2 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-4 w-4" />
              </ToastPrimitive.Close>
            </ToastPrimitive.Root>
          );
        })}
        <ToastPrimitive.Viewport
          className="fixed bottom-4 right-4 z-[100] flex max-w-[380px] flex-col gap-2 outline-none"
        />
      </ToastPrimitive.Provider>
    </Ctx.Provider>
  );
}
