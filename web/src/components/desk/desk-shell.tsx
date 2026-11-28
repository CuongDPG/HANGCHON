"use client";

import { MoreHorizontal, RotateCw, WifiOff } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { useSession } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { DESK_MORE_NAV, DESK_PRIMARY_NAV, DESK_PUBLIC_ROUTES, findDeskNav } from "@/lib/desk-nav";
import { CommandProvider } from "./command-sheet";
import { DESK_FRAME, DeskTopBar } from "./desk-topbar";
import { MoreSheet } from "./more-sheet";

/**
 * Khung bàn làm việc: chặn khi chưa đăng nhập, điều hướng dưới (điện thoại) / hàng menu trên (máy tính), nút «Nói với AI»
 * (nút nổi chỉ có icon; trang có thanh thao tác dính đáy thì nút nằm trong thanh — `AiActionButton`).
 * Trang con chỉ lo nội dung của mình; người dùng hiện tại lấy bằng `useSession().user`.
 */
export function DeskShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, status, error, refetch } = useSession();
  const [moreOpen, setMoreOpen] = useState(false);
  const active = findDeskNav(pathname);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(`${DESK_PUBLIC_ROUTES.login}?next=${encodeURIComponent(pathname)}`);
    }
  }, [status, pathname, router]);

  // Trang con luôn được render (ẩn + inert khi chưa xác nhận phiên) để Next.js dựng sẵn và kiểm được
  // điều hướng tức thì; dữ liệu vẫn an toàn vì API tự chặn khi chưa đăng nhập (401).
  const ready = status === "authenticated";
  let gate: ReactNode = null;
  if (status === "error") {
    gate = (
      <EmptyState
        tone="error"
        icon={<WifiOff />}
        title="Chưa kết nối được máy chủ"
        description={
          error && !(error instanceof ApiError && error.isNetwork)
            ? error.message
            : "Kiểm tra mạng, hoặc máy chủ đang khởi động. Đợi vài giây rồi thử lại."
        }
        action={
          <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
            Thử lại
          </Button>
        }
        className="mt-6"
      />
    );
  } else if (!ready) {
    gate = <ContentLoading />;
  }

  return (
    <div className="min-h-dvh">
      <CommandProvider enabled={ready}>
        <DeskTopBar activeKey={active?.key} user={user} ready={ready} />
        <main id="noi-dung" data-desk className={MAIN_CLASS}>
          {gate}
          <div hidden={!ready} inert={!ready}>
            {children}
          </div>
        </main>
        <DeskTabBar activeKey={active?.key} onMore={() => setMoreOpen(true)} />
      </CommandProvider>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} activeKey={active?.key} user={user} />
    </div>
  );
}

/**
 * Mọi màn bàn làm việc cùng một bề rộng (DESK_FRAME: hết bề ngang màn, thẳng mép với hàng menu trên) để chuyển màn không nhảy khung.
 * `data-desk` bật kiểu đầu trang gọn của PageHeader. Đáy chừa chỗ cho nút nổi «Nói với AI» (44px) để nút không che dòng cuối.
 */
const MAIN_CLASS = cn(
  DESK_FRAME,
  "px-4 pt-[max(16px,env(safe-area-inset-top))] pb-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+72px)] md:pt-5 md:pb-24",
);

function ContentLoading() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Đang tải">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

/** Khung tạm khi chưa biết đường dẫn/phiên (fallback của <Suspense> trong desk/(app)/layout.tsx). */
export function DeskShellFallback() {
  return (
    <div className="min-h-dvh">
      <DeskTopBar ready={false} />
      <main data-desk className={MAIN_CLASS}>
        <ContentLoading />
      </main>
      <DeskTabBar onMore={() => {}} />
    </div>
  );
}

function DeskTabBar({ activeKey, onMore }: { activeKey?: string; onMore: () => void }) {
  const moreActive = DESK_MORE_NAV.some((i) => i.key === activeKey);
  const cell = "relative flex h-full w-full flex-col items-center justify-center gap-1 px-0.5 text-[11px] leading-none transition-colors";
  return (
    <nav aria-label="Điều hướng" className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface pb-safe md:hidden">
      {/* 6 mục chính + «Thêm» ở 390px: ô co theo độ dài chữ (flex-auto) thay vì chia đều, để «Sản phẩm», «Nội dung» không chạm nhau */}
      <ul className="flex h-tabbar">
        {DESK_PRIMARY_NAV.map((item) => {
          const on = item.key === activeKey;
          const Icon = item.icon;
          return (
            <li key={item.key} className="min-w-0 flex-auto">
              <Link href={item.href} aria-current={on ? "page" : undefined} className={cn(cell, on ? "font-semibold text-accent" : "text-ink-2")}>
                {on ? <span aria-hidden className="absolute inset-x-3 top-0 h-0.5 bg-accent" /> : null}
                <Icon className="size-[22px]" strokeWidth={on ? 2.2 : 1.8} aria-hidden />
                <span className="whitespace-nowrap">{item.label}</span>
              </Link>
            </li>
          );
        })}
        <li className="min-w-0 flex-auto">
          <button type="button" onClick={onMore} aria-haspopup="dialog" className={cn(cell, moreActive ? "font-semibold text-accent" : "text-ink-2")}>
            {moreActive ? <span aria-hidden className="absolute inset-x-3 top-0 h-0.5 bg-accent" /> : null}
            <MoreHorizontal className="size-[22px]" strokeWidth={moreActive ? 2.2 : 1.8} aria-hidden />
            Thêm
          </button>
        </li>
      </ul>
    </nav>
  );
}
