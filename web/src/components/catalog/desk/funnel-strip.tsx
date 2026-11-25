import type { Funnel } from "@/lib/api/catalog";
import { cn } from "@/lib/cn";

const STEPS: { key: keyof Funnel; label: string }[] = [
  { key: "viewed", label: "đã xem" },
  { key: "compared", label: "so kỹ" },
  { key: "tried", label: "mua thử" },
  { key: "selected", label: "chọn" },
];

/** Dải số sàng lọc: đã xem → so kỹ → mua thử → chọn (e2). Dữ liệu nội bộ — chỉ hiện ở desk, không ra website. */
export function FunnelStrip({ funnel, className }: { funnel: Funnel; className?: string }) {
  const steps = STEPS.filter((s) => funnel[s.key] !== undefined && funnel[s.key] !== null);
  return (
    <ol className={cn("grid grid-cols-4 divide-x divide-line rounded-md border border-line bg-surface", className)}>
      {steps.map((s, i) => (
        <li key={s.key} className={cn("flex flex-col items-center px-1 py-2.5 text-center", i === steps.length - 1 && "text-seal")}>
          <span className="font-display text-[22px] leading-none font-extrabold tabular-nums">{funnel[s.key]}</span>
          <span className="mt-1 text-[12.5px] text-ink-2">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}
