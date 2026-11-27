"use client";

import { BarChart3, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { Badge, Button, Card, EmptyState, Money, PageHeader, SectionLabel, SkeletonList, StatTile, notifySuccess } from "@/components/ui";
import { usePerformance, useRefreshMetrics, useRunInsights } from "@/lib/api/content";
import { formatDayMonth, formatNumber, formatVndCompact } from "@/lib/format";
import { ChannelMark, ContentNav } from "./shared";

/** Đo và học (f7): bài nào ra đơn (gắn đơn qua mã bài trong link ?src=), AI rút 2–3 nhận xét cho tuần sau. */
export function PerformanceScreen() {
  const { data, isPending, error } = usePerformance();
  const refresh = useRefreshMetrics();
  const learn = useRunInsights();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Bài nào ra đơn"
        description="Số liệu cập nhật mỗi giờ."
        actions={
          <Button size="sm" variant="ghost" icon={<RefreshCw className="size-4" aria-hidden />} loading={refresh.isPending} onClick={() => refresh.mutate(undefined, { onSuccess: () => notifySuccess("Đã cập nhật số liệu") })}>
            Cập nhật
          </Button>
        }
      />
      <ContentNav />
      {isPending ? (
        <SkeletonList rows={5} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được số liệu" description={error.message} />
      ) : data ? (
        <>
          <div className="grid grid-cols-3 gap-2">
            <StatTile value={formatNumber(data.totals.posts)} label={`bài, ${data.days} ngày`} />
            <StatTile value={formatNumber(data.totals.orders)} label="đơn từ bài" />
            <StatTile value={formatVndCompact(data.totals.revenue_vnd)} label="doanh thu" />
          </div>

          <Card tone="accent" className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-accent" aria-hidden />
              <h2 className="text-[17px] font-bold">AI rút kinh nghiệm</h2>
              <span className="flex-1" />
              <Button size="sm" variant="secondary" loading={learn.isPending} onClick={() => learn.mutate(undefined, { onSuccess: () => notifySuccess("AI đã đọc số liệu và rút nhận xét") })}>
                Đọc lại
              </Button>
            </div>
            {data.insight ? (
              <>
                <p className="text-[14px] text-ink-2">
                  {formatDayMonth(data.insight.period_start)}–{formatDayMonth(data.insight.period_end)} · {data.insight.summary}
                </p>
                <ol className="flex flex-col gap-2">
                  {data.insight.findings.map((f, i) => (
                    <li key={i} className="rounded-md bg-surface p-3 text-[14px]">
                      <p className="font-semibold">{f.pattern}</p>
                      <p className="text-ink-2">Căn cứ: {f.evidence}</p>
                      <p>→ {f.recommendation}</p>
                    </li>
                  ))}
                </ol>
                <p className="text-[12.5px] text-ink-2">Nhận xét này được dùng khi AI xếp lịch và gợi ý bài tuần sau.</p>
              </>
            ) : (
              <p className="text-[14px] text-ink-2">Chưa có nhận xét. Bấm «Đọc lại» khi đã có vài bài đăng.</p>
            )}
          </Card>

          <section className="flex flex-col gap-2">
            <SectionLabel>XẾP THEO SỐ ĐƠN</SectionLabel>
            {data.posts.length === 0 ? (
              <EmptyState icon={<BarChart3 />} title="Chưa có bài nào đã đăng" description="Bài đăng xong sẽ hiện ở đây kèm số đơn và doanh thu gắn được." />
            ) : (
              <ol className="flex flex-col gap-2">
                {data.posts.map((r, i) => (
                  <li key={r.scheduled_post_id} className="flex gap-3 rounded-md border border-line bg-surface p-3">
                    <span className="w-5 shrink-0 font-display text-[17px] font-bold text-ink-3">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <ChannelMark channel={r.channel} className="size-5 text-[10px]" />
                        <span className="truncate font-semibold">{r.name ?? r.title}</span>
                      </div>
                      <p className="truncate text-[13px] text-ink-2">
                        {r.title} · {formatDayMonth(r.published_at)} · mã {r.src_code}
                      </p>
                      <p className="mt-1 flex flex-wrap gap-x-3 text-[13px] text-ink-2 tabular-nums">
                        <span>{formatNumber(r.reach)} tiếp cận</span>
                        <span>{formatNumber(r.likes)} thích</span>
                        <span>{formatNumber(r.comments)} bình luận</span>
                        <span>{formatNumber(r.clicks)} nhấp link</span>
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge tone={r.orders ? "success" : "neutral"}>{r.orders} đơn</Badge>
                      {r.revenue_vnd ? <Money value={r.revenue_vnd} compact className="text-[13px]" /> : null}
                      {r.external_url ? (
                        <a href={r.external_url} target="_blank" rel="noreferrer" aria-label="Xem bài" className="text-accent">
                          <ExternalLink className="size-4" aria-hidden />
                        </a>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
