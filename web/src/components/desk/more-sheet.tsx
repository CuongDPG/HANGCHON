"use client";

import { ChevronRight, LogOut, Palette } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/overlay";
import { useLogout, type SessionUser } from "@/lib/api/auth";
import { cn } from "@/lib/cn";
import { DESK_MORE_NAV, DESK_PUBLIC_ROUTES } from "@/lib/desk-nav";

/** Danh sách «Thêm» trên điện thoại: các khu ngoài 5 mục chính + tài khoản. */
export function MoreSheet({ open, onClose, activeKey, user }: { open: boolean; onClose: () => void; activeKey?: string; user: SessionUser | null }) {
  const logout = useLogout();
  return (
    <Sheet open={open} onClose={onClose} title="Thêm">
      <ul className="-mx-2 flex flex-col">
        {DESK_MORE_NAV.map((item) => {
          const Icon = item.icon;
          const active = item.key === activeKey;
          return (
            <li key={item.key}>
              <Link
                href={item.href}
                onClick={onClose}
                aria-current={active ? "page" : undefined}
                className={cn("flex items-center gap-3 rounded-md px-2 py-2.5 transition-colors hover:bg-soft-2", active && "bg-accent-wash")}
              >
                <span className={cn("grid size-10 shrink-0 place-items-center rounded-md bg-soft text-ink-2", active && "bg-accent text-on-accent")}>
                  <Icon className="size-5" aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-semibold">{item.label}</span>
                  <span className="block truncate text-[13px] text-ink-2">{item.description}</span>
                </span>
                <ChevronRight className="size-4 shrink-0 text-ink-3" aria-hidden />
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold">{user?.name ?? "—"}</p>
          <p className="truncate text-[13px] text-ink-2">{user?.email}</p>
        </div>
        <Button variant="secondary" size="sm" icon={<LogOut className="size-4" />} loading={logout.isPending} onClick={() => logout.mutate()}>
          Đăng xuất
        </Button>
      </div>
      <Link href={DESK_PUBLIC_ROUTES.kit} onClick={onClose} className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink">
        <Palette className="size-3.5" aria-hidden /> Bộ giao diện
      </Link>
    </Sheet>
  );
}
