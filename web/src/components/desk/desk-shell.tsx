"use client";

import { LogOut, MoreHorizontal, Palette, RotateCw, WifiOff } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Brand } from "@/components/layout/brand";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { IconButton } from "@/components/ui/icon-button";
import { useLogout, useSession } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { DESK_MORE_NAV, DESK_PRIMARY_NAV, DESK_PUBLIC_ROUTES, findDeskNav, type DeskNavItem } from "@/lib/desk-nav";
import { CommandButton } from "./command-sheet";
import { MoreSheet } from "./more-sheet";

/**
 * Khung bàn làm việc: chặn khi chưa đăng nhập, điều hướng dưới (điện thoại) / cột trái (máy tính), nút «Nói với AI».
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
      <DeskSidebar activeKey={active?.key} userName={user?.name} userEmail={user?.email} />
      <div className="md:pl-sidebar">
        <main id="noi-dung" className={cn(MAIN_CLASS, isWide(pathname) && "max-w-none")}>
          {gate}
          <div hidden={!ready} inert={!ready}>
            {children}
          </div>
        </main>
      </div>
      <DeskTabBar activeKey={active?.key} onMore={() => setMoreOpen(true)} />
      {status === "authenticated" ? <CommandButton /> : null}
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} activeKey={active?.key} user={user} />
    </div>
  );
}

/** Màn dạng bảng (nhiều cột) dùng hết bề rộng; màn danh sách/biểu mẫu giữ cột đọc vừa phải. */
const WIDE_ROUTES = [/^\/desk\/ban-chon\/?$/, /^\/desk\/noi-dung\/lich\/?$/, /^\/desk\/san-hang\/so-sanh\/[^/]+\/?$/];
function isWide(pathname: string) {
  return WIDE_ROUTES.some((r) => r.test(pathname));
}

const MAIN_CLASS =
  "mx-auto w-full max-w-[60rem] px-4 pt-[max(16px,env(safe-area-inset-top))] pb-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+88px)] md:px-8 md:pt-8 md:pb-28";

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
      <DeskSidebar />
      <div className="md:pl-sidebar">
        <main className={MAIN_CLASS}>
          <ContentLoading />
        </main>
      </div>
      <DeskTabBar onMore={() => {}} />
    </div>
  );
}

function DeskTabBar({ activeKey, onMore }: { activeKey?: string; onMore: () => void }) {
  const moreActive = DESK_MORE_NAV.some((i) => i.key === activeKey);
  const cell = "relative flex h-full w-full flex-col items-center justify-center gap-1 text-[11px] leading-none transition-colors";
  return (
    <nav aria-label="Điều hướng" className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface pb-safe md:hidden">
      <ul className="grid h-tabbar grid-cols-6">
        {DESK_PRIMARY_NAV.map((item) => {
          const on = item.key === activeKey;
          const Icon = item.icon;
          return (
            <li key={item.key}>
              <Link href={item.href} aria-current={on ? "page" : undefined} className={cn(cell, on ? "font-semibold text-accent" : "text-ink-2")}>
                {on ? <span aria-hidden className="absolute inset-x-3 top-0 h-0.5 bg-accent" /> : null}
                <Icon className="size-[22px]" strokeWidth={on ? 2.2 : 1.8} aria-hidden />
                <span className="whitespace-nowrap">{item.label}</span>
              </Link>
            </li>
          );
        })}
        <li>
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

function SidebarLink({ item, active }: { item: DeskNavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-10 items-center gap-3 rounded-md px-3 text-[15px] transition-colors",
        active ? "bg-accent-wash font-semibold text-accent" : "text-ink-2 hover:bg-soft-2 hover:text-ink",
      )}
    >
      <Icon className="size-[18px] shrink-0" strokeWidth={active ? 2.2 : 1.8} aria-hidden />
      {item.label}
    </Link>
  );
}

function DeskSidebar({ activeKey, userName, userEmail }: { activeKey?: string; userName?: string; userEmail?: string }) {
  const logout = useLogout();
  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-sidebar flex-col border-r border-line bg-surface md:flex">
      <Link href="/desk" className="mx-3 mt-5 mb-4 rounded-md px-2 py-1">
        <Brand sub="Bàn làm việc" />
      </Link>
      <nav aria-label="Điều hướng" className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-3 pb-4">
        {DESK_PRIMARY_NAV.map((item) => (
          <SidebarLink key={item.key} item={item} active={item.key === activeKey} />
        ))}
        <p className="mt-5 mb-1 px-3 text-[12px] font-semibold tracking-[0.08em] text-ink-3 uppercase">Thêm</p>
        {DESK_MORE_NAV.map((item) => (
          <SidebarLink key={item.key} item={item} active={item.key === activeKey} />
        ))}
      </nav>
      <div className="flex items-center gap-2 border-t border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          {userName ? <p className="truncate text-sm font-semibold">{userName}</p> : <Skeleton className="h-4 w-24" />}
          <p className="truncate text-[12px] text-ink-2">{userEmail}</p>
        </div>
        <Link href={DESK_PUBLIC_ROUTES.kit} aria-label="Bộ giao diện" title="Bộ giao diện" className="grid size-9 place-items-center rounded-md text-ink-2 hover:bg-soft-2 hover:text-ink">
          <Palette className="size-[18px]" aria-hidden />
        </Link>
        <IconButton label="Đăng xuất" icon={<LogOut />} size="sm" onClick={() => logout.mutate()} disabled={logout.isPending} />
      </div>
    </aside>
  );
}
