import type { Metadata } from "next";
import { Suspense } from "react";
import { ShelfResults, ShelfSkeleton } from "@/components/catalog/shelf";
import { Seal } from "@/components/ui/seal";

export const metadata: Metadata = {
  title: { absolute: "Hàng Chọn · Kệ hàng đã chọn, món nào cũng đã dùng thử" },
  description:
    "Đồ gia dụng nhỏ được chọn kỹ: xem hàng chục mẫu, mua thử, dùng thật rồi mới đóng dấu. Nói rõ cả điều chưa ưng.",
  alternates: { canonical: "/" },
  openGraph: { type: "website", locale: "vi_VN", siteName: "Hàng Chọn", title: "Hàng Chọn · Kệ hàng đã chọn" },
};

/** Trang chủ — hướng B «Kệ hàng đã chọn»: vào là thấy hàng, mỗi món có con dấu và bằng chứng đã thử. */
export default function ShelfPage({ searchParams }: PageProps<"/">) {
  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[12.5px] font-semibold tracking-[0.08em] text-accent uppercase">Kệ hàng đã chọn</p>
          <h1 className="mt-1 text-[24px] leading-tight font-extrabold [text-wrap:balance] md:text-[34px]">
            Ít món thôi. Món nào cũng đã dùng thử.
          </h1>
        </div>
        <Seal size={56} className="hidden shrink-0 sm:inline-grid" />
      </header>
      <Suspense fallback={<ShelfSkeleton />}>
        <ShelfBody searchParams={searchParams} />
      </Suspense>
      <aside className="flex items-center gap-4 rounded-md border border-line bg-surface p-4">
        <Seal chosen={1} total={24} size={56} />
        <p className="text-[14px] text-ink-2">
          <span className="font-semibold text-ink">Con dấu ĐÃ CHỌN 1/24</span> nghĩa là xem 24 món cùng loại, chỉ giữ lại 1.
          Bấm vào món để xem vì sao chọn và các món đã bị loại.
        </p>
      </aside>
    </div>
  );
}

async function ShelfBody({ searchParams }: { searchParams: PageProps<"/">["searchParams"] }) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? null;
  return <ShelfResults q={one(sp.q)?.trim() || null} nhom={one(sp.nhom)} />;
}
