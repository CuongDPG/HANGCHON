import { Suspense } from "react";
import { DeskShell, DeskShellFallback } from "@/components/desk/desk-shell";

/**
 * Mọi trang bàn làm việc cần đăng nhập nằm trong nhóm (app). Đăng nhập và /desk/kit ở ngoài nhóm này.
 * DeskShell đọc đường dẫn + phiên (dữ liệu theo request) nên được bọc <Suspense> (cacheComponents).
 */
export default function DeskAppLayout({ children }: LayoutProps<"/desk">) {
  return (
    <Suspense fallback={<DeskShellFallback />}>
      <DeskShell>{children}</DeskShell>
    </Suspense>
  );
}
