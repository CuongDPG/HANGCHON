import { cn } from "@/lib/cn";

/** Chữ «Hàng Chọn» + dấu tròn nhỏ. `sub` là dòng phụ (vd. "Bàn làm việc"). */
export function Brand({ sub, className }: { sub?: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BrandMark className="size-7" />
      <span className="flex flex-col leading-none">
        <span className="font-display text-[19px] font-extrabold tracking-[0.01em]">Hàng Chọn</span>
        {sub ? <span className="mt-1 text-[11.5px] font-medium tracking-[0.04em] text-ink-2">{sub}</span> : null}
      </span>
    </span>
  );
}

/** Dấu nhận diện: vòng dấu đỏ son, nét đứt bên trong, dấu tích ở giữa. Không phụ thuộc phông chữ. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("shrink-0 text-seal", className)} aria-hidden>
      <g transform="rotate(-8 16 16)" fill="none" stroke="currentColor">
        <circle cx="16" cy="16" r="14" strokeWidth="2.4" />
        <circle cx="16" cy="16" r="10.6" strokeWidth="1" strokeDasharray="2.2 2" opacity="0.7" />
        <path d="M10.5 16.4l3.7 3.7 7.4-7.6" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}
