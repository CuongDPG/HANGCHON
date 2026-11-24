import { Suspense } from "react";
import { Brand } from "@/components/layout/brand";
import { Skeleton } from "@/components/ui/feedback";
import { LoginForm } from "./login-form";

export const metadata = { title: "Đăng nhập" };

export default function DeskLoginPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Brand sub="Bàn làm việc" />
        </div>
        <div className="rounded-md border border-line bg-surface p-6 shadow-sm">
          <h1 className="text-2xl font-bold">Đăng nhập</h1>
          <p className="mt-1 mb-5 text-[15px] text-ink-2">Dành cho người chọn hàng và người phụ giúp.</p>
          {/* LoginForm đọc ?next= bằng useSearchParams → cần <Suspense> */}
          <Suspense fallback={<Skeleton className="h-56 w-full" />}>
            <LoginForm />
          </Suspense>
        </div>
      </div>
    </main>
  );
}
