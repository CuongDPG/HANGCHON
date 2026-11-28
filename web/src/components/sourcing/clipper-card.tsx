"use client";

import { Send } from "lucide-react";
import { useEffect, useRef } from "react";
import { Card, buttonClasses } from "@/components/ui";
import { bookmarkletHref } from "@/lib/clipper/bookmarklet";

export const CLIPPER_CARD_ID = "nut-gui";

/**
 * Cài đặt → Nguồn hàng: nút «Gửi sang Hàng Chọn» để chị kéo lên thanh dấu trang (máy tính). Sàn chặn máy chủ (captcha,
 * bắt đăng nhập) thì chị mở trang món, bấm nút: trình duyệt của chị đọc trang và gửi sang (xem `lib/clipper`).
 */
export function ClipperCard() {
  const ref = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    // React chặn href `javascript:` trong JSX → gán thẳng vào DOM; origin theo trang đang mở (dev / bản chạy thật)
    ref.current?.setAttribute("href", bookmarkletHref(window.location.origin));
  }, []);
  return (
    <Card id={CLIPPER_CARD_ID} role="region" aria-label="Nút Gửi sang Hàng Chọn" className="flex scroll-mt-20 flex-col gap-3 border border-line">
      <h2 className="text-[18px]">Nút «Gửi sang Hàng Chọn»</h2>
      <a
        ref={ref}
        draggable
        onClick={(e) => e.preventDefault()}
        className={buttonClasses({ variant: "secondary", size: "sm", className: "cursor-grab self-start" })}
      >
        <Send className="size-4" aria-hidden />
        Gửi sang Hàng Chọn
      </a>
      <ol className="list-decimal pl-5 text-[14px] text-ink-2">
        <li>Kéo nút trên lên thanh dấu trang của trình duyệt (máy tính).</li>
        <li>Mở trang món trên 1688, Taobao, Tmall, Amazon, Rakuten hoặc trang bất kỳ.</li>
        <li>Bấm «Gửi sang Hàng Chọn» trên thanh dấu trang.</li>
      </ol>
    </Card>
  );
}
