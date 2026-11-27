"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

/** Các mục trong khu Khách (h1–h8). Khu Khách có một mục trên thanh điều hướng nên mục con nằm ở hàng này. */
export const KHACH_SECTIONS = [
  { key: "inbox", href: "/desk/khach", label: "Hộp thư" },
  { key: "book", href: "/desk/khach/so-khach", label: "Sổ khách" },
  { key: "regulars", href: "/desk/khach/khach-quen", label: "Khách quen" },
  { key: "reorder", href: "/desk/khach/nhac-mua-lai", label: "Nhắc mua lại" },
  { key: "referral", href: "/desk/khach/gioi-thieu", label: "Giới thiệu bạn" },
  { key: "testers", href: "/desk/khach/thu-hang", label: "Thử hàng" },
  { key: "cotrial", href: "/desk/khach/dung-thu", label: "Người dùng thử" },
] as const;

export type KhachSection = (typeof KHACH_SECTIONS)[number]["key"];

/** Hàng liên kết dạng chip, cuộn ngang trên điện thoại. */
export function KhachNav({ active }: { active: KhachSection }) {
  const ref = useRef<HTMLElement>(null);
  // Mục đang chọn luôn nằm trong tầm nhìn khi hàng chip cuộn ngang (điện thoại)
  useEffect(() => {
    const nav = ref.current;
    if (!nav) return;
    // Trang có thể dựng lúc còn ẩn (chờ phiên đăng nhập) → đợi hàng chip có kích thước rồi mới cuộn
    const reveal = () => {
      const el = nav.querySelector<HTMLElement>('[aria-current="page"]');
      if (!el || nav.clientWidth === 0) return;
      const n = nav.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      if (r.right > n.right || r.left < n.left) nav.scrollLeft += r.left - n.left - 16;
    };
    reveal();
    const ro = new ResizeObserver(reveal);
    ro.observe(nav);
    return () => ro.disconnect();
  }, [active]);
  return (
    <nav ref={ref} aria-label="Mục trong khu Khách" className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0">
      {KHACH_SECTIONS.map((s) => {
        const on = s.key === active;
        return (
          <Link
            key={s.key}
            href={s.href}
            aria-current={on ? "page" : undefined}
            className={cn(
              "inline-flex h-9 shrink-0 items-center rounded-md border px-3 text-sm whitespace-nowrap transition-colors",
              on ? "border-ink bg-ink text-paper" : "border-line-strong bg-surface text-ink hover:border-ink-3",
            )}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}
