import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type CardTone = "default" | "soft" | "accent" | "danger" | "plain";

const tones: Record<CardTone, string> = {
  default: "border border-line bg-surface",
  /** Nền phụ ánh chàm: khối «Vì sao mình chọn», «AI đã tự làm». */
  soft: "bg-soft",
  /** Viền trái chàm: khối nhấn (đợt đang mở, việc cần chị để ý). */
  accent: "border border-line border-l-[3px] border-l-accent bg-surface",
  /** Viền trái đỏ son: khiếu nại, việc gấp. */
  danger: "border border-line border-l-[3px] border-l-seal bg-surface",
  plain: "",
};

type CardProps = ComponentProps<"div"> & {
  tone?: CardTone;
  /** Bỏ padding mặc định (khi bên trong là ảnh tràn viền hoặc DataList). */
  flush?: boolean;
};

export function Card({ tone = "default", flush = false, className, ...props }: CardProps) {
  return <div className={cn("rounded-md", tones[tone], !flush && "p-4", className)} {...props} />;
}

/** Thẻ bấm được, dẫn sang trang khác. */
export function CardLink({
  tone = "default",
  flush = false,
  className,
  ...props
}: ComponentProps<typeof Link> & { tone?: CardTone; flush?: boolean }) {
  return (
    <Link
      className={cn("block rounded-md transition-colors hover:border-ink-3", tones[tone], !flush && "p-4", className)}
      {...props}
    />
  );
}

/** Hàng tiêu đề trong thẻ: tiêu đề trái, thao tác/nhãn phải. */
export function CardHeader({ title, aside, className }: { title: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-2 flex items-center justify-between gap-3", className)}>
      <h3 className="min-w-0 text-[15px] font-semibold [text-wrap:pretty]">{title}</h3>
      {aside ? <div className="shrink-0">{aside}</div> : null}
    </div>
  );
}

/** Tiêu đề nhỏ cho một nhóm nội dung trong trang (vd. «HÀNG ĐANG VỀ»). */
export function SectionLabel({ children, aside, className }: { children: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between gap-3", className)}>
      <h2 className="font-sans text-[12.5px] font-semibold tracking-[0.08em] text-ink-2 uppercase">{children}</h2>
      {aside}
    </div>
  );
}
