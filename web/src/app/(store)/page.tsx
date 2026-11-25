import type { Metadata } from "next";
import { Suspense } from "react";
import { ShelfResults, ShelfSkeleton } from "@/components/catalog/shelf";
import { Seal } from "@/components/ui/seal";
import { catalogApi } from "@/lib/api/catalog";
import { formatNumber } from "@/lib/format";

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
        <Suspense fallback={null}>
          <ShelfSeal />
        </Suspense>
      </header>
      <Suspense fallback={<ShelfSkeleton />}>
        <ShelfBody searchParams={searchParams} />
      </Suspense>
      <aside className="flex items-center gap-4 rounded-md border border-line bg-surface p-4">
        <Seal chosen={1} total={24} size={56} />
        <p className="text-[14px] text-ink-2">
          <span className="font-semibold text-ink">Con dấu ĐÃ CHỌN 1/24</span> nghĩa là xem 24 món cùng loại, chỉ giữ lại 1.
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

/** Con dấu ở đầu kệ mang số thật của Bàn chọn: đã chọn bao nhiêu món trong bao nhiêu món đã xem. */
async function ShelfSeal() {
  const stats = await catalogApi
    .about()
    .then((a) => a.stats)
    .catch(() => null);
  if (!stats || !stats.viewed || !stats.chosen) return null;
  return (
    <div className="hidden shrink-0 items-center gap-3 sm:flex">
      <p className="text-right text-[13px] leading-snug text-ink-2">
        <span className="block">
          Đã chọn <span className="font-semibold text-ink">{formatNumber(stats.chosen)}</span> món
        </span>
        <span className="block">trong {formatNumber(stats.viewed)} món đã xem</span>
      </p>
      {/* tỉ lệ dài (vd. 38/1240) không vừa lòng dấu: chữ bên cạnh đã ghi đủ số */}
      {`${stats.chosen}/${stats.viewed}`.length <= 5 ? <Seal chosen={stats.chosen} total={stats.viewed} size={64} /> : <Seal size={64} />}
    </div>
  );
}
