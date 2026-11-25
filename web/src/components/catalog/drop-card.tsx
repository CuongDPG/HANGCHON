import { CalendarClock, PackageCheck } from "lucide-react";
import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import type { DropSummary } from "@/lib/api/catalog";
import { formatDayMonth } from "@/lib/format";
import { Countdown } from "./countdown";
import { RemindButton } from "./remind-button";
import { Stars } from "./stars";

/** Đợt đang mở: hạn chót và số suất là lý do thật để quyết định sớm; ngày hàng về nói ngay từ đầu. */
export function OpenDropCard({ d, headingLevel = 2 }: { d: DropSummary; headingLevel?: 2 | 3 }) {
  const H = headingLevel === 2 ? "h2" : "h3";
  const left = d.slots_total !== null ? Math.max(0, d.slots_total - d.slots_reserved) : null;
  return (
    <Card tone="accent" className="flex flex-col gap-3">
      <p className="text-[12.5px] font-semibold tracking-[0.08em] text-accent uppercase">Mua chung · {d.label} · Đang mở</p>
      <H className="text-[20px] leading-tight font-bold">{d.title}</H>
      <ImageBox src={d.cover?.webp["800"] ?? d.cover?.src} alt="" ratio="16/9" placeholder={`${d.item_count} món trong đợt`} />
      <div className="flex items-baseline justify-between gap-3 text-[15px]">
        {d.closes_at ? <Countdown until={d.closes_at} className="font-semibold" /> : <span />}
        {d.slots_total !== null ? (
          <span className="tabular-nums text-ink-2">
            {d.slots_reserved}/{d.slots_total} suất
          </span>
        ) : null}
      </div>
      {d.slots_total ? (
        <ProgressBar value={d.slots_reserved} max={d.slots_total} label={`${d.slots_reserved} trên ${d.slots_total} suất đã đặt`} />
      ) : null}
      {d.expected_arrival_date ? (
        <p className="flex items-center gap-1.5 text-[14px] text-ink-2">
          <CalendarClock className="size-4" aria-hidden /> Hàng về dự kiến {formatDayMonth(d.expected_arrival_date)}
          {left !== null ? ` · còn ${left} suất` : ""}
        </p>
      ) : null}
      <ButtonLink href={`/dot/${d.slug}`} block>
        Xem {d.item_count} món trong đợt
      </ButtonLink>
    </Card>
  );
}

export function UpcomingDropRow({ d }: { d: DropSummary }) {
  return (
    <div className="flex items-center gap-3 py-3">
      <div className="w-14 shrink-0">
        <ImageBox src={d.cover?.webp["400"] ?? d.cover?.src_small} alt="" ratio="1/1" />
      </div>
      <div className="min-w-0 flex-1">
        <Link href={`/dot/${d.slug}`} className="text-[15px] font-semibold hover:underline">
          {d.label} · {d.title}
        </Link>
        <p className="text-[13px] text-ink-2">{d.opens_at ? `Mở ${formatDayMonth(d.opens_at)}` : "Sắp mở"}</p>
      </div>
      <RemindButton slug={d.slug} title={`${d.label} · ${d.title}`} />
    </div>
  );
}

export function ArrivedDropRow({ d }: { d: DropSummary }) {
  return (
    <Link href={`/dot/${d.slug}`} className="flex items-center gap-3 py-3 hover:bg-soft-2/40">
      <div className="w-14 shrink-0">
        <ImageBox src={d.cover?.webp["400"] ?? d.cover?.src_small} alt="" ratio="1/1" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold">
          {d.label} · {d.title}
        </p>
        <p className="flex flex-wrap items-center gap-x-1.5 text-[13px] text-ink-2">
          <PackageCheck className="size-3.5" aria-hidden />
          {d.order_count} đơn
          {d.rating_avg ? (
            <>
              {" · "}
              <Stars value={d.rating_avg} /> {d.rating_avg.toLocaleString("vi-VN")}/5 từ {d.review_count} đánh giá
            </>
          ) : null}
        </p>
      </div>
    </Link>
  );
}
