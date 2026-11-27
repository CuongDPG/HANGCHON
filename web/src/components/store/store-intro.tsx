import type { ReactNode } from "react";

/**
 * Đầu trang của bốn mục menu website (Kệ hàng, Mua chung, Nhờ tìm, Dùng thử): dòng nhỏ là tên mục, `<h1>` là câu
 * khẩu hiệu cỡ lớn. Thay cho `PageHeader` ở các trang này (mỗi trang vẫn đúng một `<h1>`).
 */
export function StoreIntro({ eyebrow, title, aside, children }: { eyebrow: string; title: string; aside?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex items-end justify-between gap-4">
      <div className="min-w-0">
        <p className="text-[12.5px] font-semibold tracking-[0.08em] text-accent uppercase">{eyebrow}</p>
        <h1 className="mt-1 text-[24px] leading-tight font-extrabold [text-wrap:balance] md:text-[34px]">{title}</h1>
        {children ? <div className="mt-2 max-w-prose text-[15px] text-ink-2">{children}</div> : null}
      </div>
      {aside}
    </header>
  );
}
