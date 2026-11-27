"use client";

import Link from "next/link";
import { Fragment, useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

/** Một mục tầng 1 của khu desk (một trang riêng). `count`: số việc cần chị xem (vd. cảnh báo), không có thì ẩn. */
export type PageSection = { key: string; href: string; label: string; count?: number };

/**
 * «Tiêu đề là tab» trên hàng tiêu đề: `Mục A | Mục B | Mục C`. Mục đang mở là h1 (đậm, màu chữ chính),
 * các mục khác là liên kết mờ. Điện thoại: hàng cuộn ngang, mục đang mở tự cuộn vào tầm nhìn.
 */
export function SectionTitle({ sections, active }: { sections: readonly PageSection[]; active?: string }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const nav = ref.current;
    if (!nav) return;
    // trang có thể dựng lúc còn ẩn (chờ phiên đăng nhập) → đợi có kích thước rồi mới cuộn
    const reveal = () => {
      const el = nav.querySelector<HTMLElement>('[aria-current="page"]');
      if (!el || nav.clientWidth === 0) return;
      const n = nav.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      if (r.right > n.right || r.left < n.left) nav.scrollLeft += r.left - n.left - 8;
    };
    reveal();
    const ro = new ResizeObserver(reveal);
    ro.observe(nav);
    return () => ro.disconnect();
  }, [active]);
  return (
    <nav
      ref={ref}
      aria-label="Mục trong khu"
      className="flex min-w-0 items-center gap-x-2.5 overflow-x-auto [scrollbar-width:none] md:gap-x-3"
    >
      {sections.map((s, i) => (
        <Fragment key={s.key}>
          {i > 0 ? (
            <span aria-hidden className="shrink-0 text-[18px] font-light text-line-strong">
              |
            </span>
          ) : null}
          {s.key === active ? (
            <h1 aria-current="page" className="flex shrink-0 items-center gap-1.5 text-[21px] leading-tight font-bold whitespace-nowrap text-ink md:text-[22px]">
              {s.label}
              <SectionCount count={s.count} />
            </h1>
          ) : (
            <Link
              href={s.href}
              className={cn(
                "flex shrink-0 items-center gap-1.5 font-display text-[21px] leading-tight font-medium tracking-[0.01em] whitespace-nowrap text-ink-2 transition-colors hover:text-ink md:text-[22px]",
              )}
            >
              {s.label}
              <SectionCount count={s.count} />
            </Link>
          )}
        </Fragment>
      ))}
    </nav>
  );
}

function SectionCount({ count }: { count?: number }) {
  if (!count) return null;
  return <span className="rounded-sm bg-review-wash px-1.5 font-sans text-[12px] leading-5 font-semibold text-review tabular-nums">{count}</span>;
}
