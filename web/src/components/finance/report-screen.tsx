"use client";

import { BarChart3, RefreshCw, RotateCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Button,
  Card,
  EmptyState,
  InlineSelect,
  LevelTag,
  PageHeader,
  SectionLabel,
  SkeletonList,
  StatTile,
  notifySuccess,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useGenerateReport, useReports, type WeeklyReport } from "@/lib/api/finance";
import { formatNumber, formatVndCompact } from "@/lib/format";

const CHANNELS: Record<string, string> = { facebook: "Facebook", instagram: "Instagram", threads: "Threads", tiktok: "TikTok", zalo: "Zalo", zalo_oa: "Zalo", web: "Website" };

function dm(iso: string): string {
  return `${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))}`;
}

function weekLabel(r: WeeklyReport): string {
  return `Tuần ${r.metrics.iso_week ?? ""} · ${dm(r.week_start)}–${dm(r.week_end)}`.replace("Tuần  · ", "");
}

function minutesText(m: number): string {
  if (m < 60) return `${m} phút`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} giờ ${m % 60} phút` : `${h} giờ`;
}

/** Báo cáo tuần (i5): bốn con số, món và bài ra đơn, AI rút ra gì, thời gian chị dành cho việc duyệt. */
export function ReportScreen() {
  const { data, isPending, error, refetch } = useReports();
  const [id, setId] = useState<string | null>(null);
  const { user } = useSession();
  const gen = useGenerateReport();
  const reports = data?.items ?? [];
  const report = reports.find((r) => r.id === id) ?? reports[0];

  async function regenerate() {
    const r = await gen.mutateAsync(undefined);
    setId(r.id);
    notifySuccess("Đã lập báo cáo tuần này");
  }

  const regen = isOwner(user) ? (
    <Button variant="secondary" size="sm" icon={<RefreshCw className="size-4" />} loading={gen.isPending} onClick={regenerate}>
      Lập lại tuần này
    </Button>
  ) : null;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow={report && reports.length < 2 ? weekLabel(report) : undefined}
        title="Báo cáo tuần"
        description="Tự lập 6 giờ sáng thứ Hai cho tuần trước."
      />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được báo cáo"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : !report ? (
        <EmptyState
          icon={<BarChart3 />}
          title="Chưa có báo cáo tuần nào"
          description="Báo cáo đầu tiên tự lập vào sáng thứ Hai tới. Chị cũng có thể lập ngay cho tuần này."
          action={regen}
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            {reports.length > 1 ? (
              <InlineSelect
                aria-label="Chọn tuần"
                appearance="inline"
                value={report.id}
                onChange={setId}
                options={reports.map((r) => ({ value: r.id, label: weekLabel(r) }))}
              />
            ) : (
              <span />
            )}
            {regen}
          </div>
          <ReportBody r={report} />
        </>
      )}
    </div>
  );
}

function ReportBody({ r }: { r: WeeklyReport }) {
  const margin = r.metrics.gross_margin_pct;
  const returning = r.metrics.returning_order_pct;
  const missing = r.metrics.cogs_missing_items ?? 0;
  const top = r.product_margins.slice(0, 5);
  const insight = r.metrics.insight_status;
  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <StatTile value={formatVndCompact(r.revenue_vnd)} label="doanh thu" hint={`${r.order_count} đơn`} />
        <StatTile
          value={formatVndCompact(r.gross_profit_vnd)}
          label={margin !== null && margin !== undefined ? `lãi gộp · ${formatNumber(margin)}%` : "lãi gộp"}
          hint={missing ? `${missing} món chưa có giá vốn` : undefined}
        />
        <StatTile
          value={returning !== null && returning !== undefined ? `${formatNumber(returning)}%` : "—"}
          label="đơn từ khách cũ"
          hint={r.order_count ? `${r.returning_customer_count}/${r.customer_count} khách` : undefined}
        />
        <StatTile value={formatVndCompact(r.ai_cost_vnd)} label="chi phí AI" href="/desk/tu-chu/chi-phi-ai" />
      </div>

      <Card>
        <SectionLabel className="mb-2">Món ra đơn nhiều nhất</SectionLabel>
        {top.length ? (
          <ul className="flex flex-col">
            {top.map((m) => (
              <li key={m.product_id ?? m.name} className="flex items-baseline justify-between gap-3 py-1.5 text-[15px]">
                <span className="min-w-0">{m.name}</span>
                <span className="shrink-0 text-right tabular-nums">
                  {m.orders} đơn
                  {m.margin_pct !== null ? <span className="text-ink-2"> · biên {formatNumber(m.margin_pct)}%</span> : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[14px] text-ink-2">Tuần này chưa có đơn nào vào sổ.</p>
        )}
      </Card>

      <Card>
        <SectionLabel className="mb-2">Bài kéo đơn nhiều nhất</SectionLabel>
        {r.top_posts.length ? (
          <ul className="flex flex-col gap-1.5">
            {r.top_posts.map((p) => (
              <li key={p.scheduled_post_id} className="text-[15px]">
                «{p.title}» · {CHANNELS[p.channel] ?? p.channel} · <b>{p.orders} đơn</b>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[14px] text-ink-2">Chưa đo được bài nào ra đơn trong tuần.</p>
        )}
      </Card>

      <Card tone="soft" className="flex flex-col gap-2">
        <LevelTag level="auto" className="self-start">
          AI rút ra
        </LevelTag>
        {r.highlights.length ? (
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[15px]">
            {r.highlights.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        ) : insight === "pending" ? (
          <p className="text-[14px] text-ink-2">
            Nhận xét của AI đang chờ chị duyệt.{" "}
            <Link href="/desk/duyet?action=finance.weekly_insights" className="font-semibold text-accent">
              Xem →
            </Link>
          </p>
        ) : r.metrics.insight_error ? (
          <p className="text-[14px] text-ink-2">AI chưa viết được nhận xét: {r.metrics.insight_error}</p>
        ) : (
          <p className="text-[14px] text-ink-2">Chưa có nhận xét cho tuần này.</p>
        )}
      </Card>

      <p className="text-[14px] text-ink-2">
        {r.metrics.review_decisions
          ? `Tuần này chị dành khoảng ${minutesText(r.metrics.review_minutes ?? 0)} cho việc duyệt (${r.metrics.review_decisions} lần quyết).`
          : "Tuần này chị chưa phải duyệt việc nào."}
        {r.expenses_vnd ? ` Chi phí ghi sổ: ${formatVndCompact(r.expenses_vnd)}.` : ""}
      </p>
    </>
  );
}
