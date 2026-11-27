import type { Metadata } from "next";
import { Suspense } from "react";
import { ShelfResults, ShelfSkeleton } from "@/components/catalog/shelf";
import { StoreIntro } from "@/components/store/store-intro";
import { Seal } from "@/components/ui/seal";

export const metadata: Metadata = {
  title: { absolute: "Hàng Chọn · Kệ hàng: ít nhưng mà chất" },
  description:
    "Đồ gia dụng nhỏ được chọn kỹ: mua về, dùng thật rồi mới đóng dấu. Nói rõ cả điều chưa ưng.",
  alternates: { canonical: "/" },
  openGraph: { type: "website", locale: "vi_VN", siteName: "Hàng Chọn", title: "Hàng Chọn · Kệ hàng" },
};

/** Trang chủ — hướng B «Kệ hàng đã chọn»: vào là thấy hàng, mỗi món có con dấu và bằng chứng đã thử. */
export default function ShelfPage({ searchParams }: PageProps<"/">) {
  return (
    <div className="flex flex-col gap-6">
      <StoreIntro eyebrow="Kệ hàng" title="Ít nhưng mà chất..." aside={<Seal size={64} className="hidden sm:inline-grid" />} />
      <Suspense fallback={<ShelfSkeleton />}>
        <ShelfBody searchParams={searchParams} />
      </Suspense>
      <aside className="flex items-center gap-4 rounded-md border border-line bg-surface p-4">
        <Seal size={56} />
        <p className="text-[14px] text-ink-2">
          <span className="font-semibold text-ink">Con dấu ĐÃ CHỌN</span> nghĩa là mình đã mua về, dùng thật rồi mới giữ lại.
          Bấm vào món để xem vì sao mình chọn.
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
