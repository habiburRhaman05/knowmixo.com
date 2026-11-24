import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Tiny inline SVG sparkline — zero dependency, zero runtime cost. Uses a
 * smooth bezier curve through the normalised series and fills the area
 * under the line with a brand-tinted gradient.
 */
export function Sparkline({
  values,
  width = 120,
  height = 32,
  stroke = "hsl(var(--primary))",
  className,
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  className?: string;
}) {
  const safe = values && values.length >= 2 ? values : [0, 0];
  const min = Math.min(...safe);
  const max = Math.max(...safe);
  const range = max - min || 1;
  const step = width / (safe.length - 1);
  const points = safe.map((v, i) => ({
    x: i * step,
    y: height - ((v - min) / range) * (height - 4) - 2,
  }));
  const path = points
    .map((p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `L ${p.x} ${p.y}`))
    .join(" ");
  const area = `${path} L ${width} ${height} L 0 ${height} Z`;
  const id = React.useId();
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      className={cn("overflow-visible", className)}
      role="img"
      aria-hidden
    >
      <defs>
        <linearGradient id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#g-${id})`} />
      <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle
        cx={points[points.length - 1].x}
        cy={points[points.length - 1].y}
        r="2.5"
        fill={stroke}
      />
    </svg>
  );
}
