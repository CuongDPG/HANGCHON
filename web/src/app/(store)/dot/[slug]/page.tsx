import type { Metadata } from "next";
import { CalendarClock, Hourglass } from "lucide-react";
import { notFound } from "next/navigation";
import { Suspense, cache } from "react";
import { Countdown } from "@/components/catalog/countdown";
import { ProductCard } from "@/components/catalog/product-card";
import { RemindButton } from "@/components/catalog/remind-button";
import { Stars } from "@/components/catalog/stars";
import { Card } from "@/components/ui/card";
import { ProgressBar, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { catalogApi, type DropDetail } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";
import { formatDayMonth } from "@/lib/format";

const getDrop = cache(async (slug: string): Promise<DropDetail> => {
  try {
    return await catalogApi.drop(slug);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
});

export async function generateMetadata({ params }: PageProps<"/dot/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const d = await getDrop(slug);
  return {
    title: `${d.label}: ${d.title}`,
    description: d.description ?? `${d.item_count} món trong đợt${d.expected_arrival_date ? `, hàng về dự kiến ${formatDayMonth(d.expected_arrival_date)}` : ""}.`,
    alternates: { canonical: `/dot/${d.slug}` },
  };
}

export default function DropPage({ params }: PageProps<"/dot/[slug]">) {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <DropBody params={params} />
    </Suspense>
  );
}

const STATUS_WORD: Record<string, string> = {
  open: "Đang mở",
  scheduled: "Sắp mở",
  closed: "Đã chốt",
  sourcing: "Đang đặt hàng",
  arriving: "Hàng đang về",
  fulfilling: "Đã về",
  completed: "Đã về",
};

async function DropBody({ params }: { params: PageProps<"/dot/[slug]">["params"] }) {
  const { slug } = await params;
  const d = await getDrop(slug);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow={`${d.label} · ${STATUS_WORD[d.status] ?? d.status}`} title={d.title} description={d.description ?? undefined} backHref="/dot" />
      <Card tone={d.status === "open" ? "accent" : "default"} className="flex flex-col gap-2.5">
        {d.status === "open" && d.closes_at ? (
          <p className="flex items-center gap-2 text-[16px] font-semibold">
            <Hourglass className="size-4" aria-hidden /> <Countdown until={d.closes_at} />
          </p>
        ) : null}
        {d.status === "scheduled" ? (
          <div className="flex items-center justify-between gap-3">
            <p className="text-[15px]">{d.opens_at ? `Mở ${formatDayMonth(d.opens_at)}` : "Sắp mở"}</p>
            <RemindButton slug={d.slug} title={`${d.label} · ${d.title}`} />
          </div>
        ) : null}
        {d.slots_total ? (
          <>
            <ProgressBar value={d.slots_reserved} max={d.slots_total} label={`${d.slots_reserved} trên ${d.slots_total} suất`} />
            <p className="text-[14px] tabular-nums text-ink-2">
              {d.slots_reserved}/{d.slots_total} suất đã đặt
            </p>
          </>
        ) : null}
        <p className="flex items-center gap-1.5 text-[14px] text-ink-2">
          <CalendarClock className="size-4" aria-hidden />
          {d.actual_arrival_date
            ? `Hàng đã về ${formatDayMonth(d.actual_arrival_date)}`
            : d.expected_arrival_date
              ? `Hàng về dự kiến ${formatDayMonth(d.expected_arrival_date)}`
              : "Ngày hàng về: chị sẽ báo"}
          {d.deposit_pct ? ` · đặt cọc ${d.deposit_pct}%` : ""}
        </p>
        {d.rating_avg ? (
          <p className="flex items-center gap-1.5 text-[14px] text-ink-2">
            <Stars value={d.rating_avg} /> {d.rating_avg.toLocaleString("vi-VN")}/5 từ {d.review_count} đánh giá · {d.order_count} đơn
          </p>
        ) : null}
      </Card>
      <section aria-label="Các món trong đợt">
        <ul className="grid grid-cols-2 gap-x-3 gap-y-6 md:grid-cols-3 lg:grid-cols-4">
          {d.items.map((p) => (
            <li key={p.id} className="min-w-0">
              <ProductCard product={p} />
              {p.slots_left !== null && d.status === "open" ? (
                <p className="mt-1 text-[12.5px] text-ink-2">Còn {p.slots_left}/{p.slots_total} suất</p>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
