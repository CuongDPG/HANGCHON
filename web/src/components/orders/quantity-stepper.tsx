"use client";

import { Minus, Plus } from "lucide-react";
import { IconButton } from "@/components/ui";
import { cn } from "@/lib/cn";

/** Chọn số lượng − n +. */
export function QuantityStepper({
  value,
  onChange,
  min = 1,
  max = 99,
  label = "Số lượng",
  size = "md",
  className,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  label?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex items-center rounded-md border border-line-strong bg-surface", className)}>
      <IconButton label="Bớt một" icon={<Minus />} size="sm" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min} />
      <output aria-live="polite" className={cn("min-w-8 text-center font-semibold tabular-nums", size === "sm" ? "text-[14px]" : "text-[15px]")}>
        {value}
      </output>
      <IconButton label="Thêm một" icon={<Plus />} size="sm" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} />
    </div>
  );
}
