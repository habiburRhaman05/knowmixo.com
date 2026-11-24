import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  invalid?: boolean;
};

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", invalid, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          "flex h-10 w-full rounded-lg border bg-card px-3 py-2 text-sm text-foreground input-elevated transition-[border-color,box-shadow,background-color] duration-150 ease-out",
          "placeholder:text-muted-foreground/70",
          "hover:border-muted-foreground/30",
          "focus-visible:outline-none focus-visible:border-primary focus-visible:shadow-[0_0_0_4px_hsl(var(--ring)/0.14),0_1px_0_0_hsl(0_0%_100%/0.6)_inset]",
          "disabled:cursor-not-allowed disabled:opacity-60",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          invalid
            ? "border-destructive focus-visible:border-destructive focus-visible:shadow-[0_0_0_4px_hsl(var(--destructive)/0.14)]"
            : "border-input",
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
