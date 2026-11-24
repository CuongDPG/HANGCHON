"use client";

import { CircleCheck, Gauge, RotateCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Button,
  Card,
  EmptyState,
  LevelTag,
  PageHeader,
  SectionLabel,
  Skeleton,
  SkeletonList,
  StatTile,
} from "@/components/ui";
import { useToday, type ApprovalItem, type Stat } from "@/lib/api/control";
import { formatNumber, formatVndCompact, formatWeekday } from "@/lib/format";
import { ApprovalRow } from "./approval-row";
import { ApprovalSheet } from "./approval-sheet";

/** Số đã hiện ở khối trên, không lặp lại ở lưới số liệu. */
const HIDDEN_STATS = new Set(["control.pending", "control.ai_done_today"]);

function statValue(s: Stat): string {
  if (typeof s.value === "string") return s.value;
  if (s.format === "vnd") return formatVndCompact(s.value);
  if (s.format === "percent") return `${formatNumber(s.value)}%`;
  return formatNumber(s.value);
}

/** «Hôm nay» (i1): việc chờ chị ở trên, việc AI đã tự làm ở dưới, rồi số liệu trong ngày. */
export function TodayScreen() {
  const { data, isPending, error, refetch, isRefetching } = useToday();
  const [open, setOpen] = useState<ApprovalItem | null>(null);

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Hôm nay" />
        <Skeleton className="h-4 w-32" />
        <SkeletonList rows={3} />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Hôm nay" />
        <EmptyState
          tone="error"
          title="Chưa tải được màn hình Hôm nay"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} loading={isRefetching} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      </div>
    );
  }

  const decide = data.pending.items.filter((i) => i.locked);
  const review = data.pending.items.filter((i) => !i.locked);
  const more = data.pending.total - data.pending.items.length;
  const stats = data.stats.filter((s) => !HIDDEN_STATS.has(s.key));
  const cost = data.ai_cost;
  const costWarn = cost.budget_vnd > 0 && cost.used_pct >= 80;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader eyebrow={formatWeekday(data.date)} title="Hôm nay" />

      {costWarn ? (
        <Card tone={cost.used_pct >= 100 ? "danger" : "accent"} className="flex items-start gap-3">
          <Gauge className="mt-0.5 size-5 shrink-0 text-review" aria-hidden />
          <div className="min-w-0 flex-1 text-[14px]">
            <p className="font-semibold">
              {cost.used_pct >= 100 ? "AI đã chạm trần chi phí tháng này" : `Chi phí AI đã dùng ${formatNumber(cost.used_pct)}% trần tháng`}
            </p>
            <p className="text-ink-2">
              {formatVndCompact(cost.spent_vnd)} / {formatVndCompact(cost.budget_vnd)}.{" "}
              <Link href="/desk/tu-chu/chi-phi-ai" className="font-semibold text-accent">
                Xem chi tiết →
              </Link>
            </p>
          </div>
        </Card>
      ) : null}

      <section className="flex flex-col gap-3" aria-labelledby="viec-cho-chi">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="viec-cho-chi" className="text-[20px] font-bold">
            {data.pending.total ? `${data.pending.total} việc chờ chị` : "Không có việc chờ chị"}
          </h2>
          {data.pending.total ? (
            <Link href="/desk/duyet" className="shrink-0 text-[14px] font-semibold text-accent">
              Tất cả →
            </Link>
          ) : null}
        </div>
        {data.pending.total === 0 ? (
          <Card tone="soft" className="flex items-center gap-3 text-[15px]">
            <CircleCheck className="size-5 shrink-0 text-auto" aria-hidden />
            Chị đã xử lý hết. AI sẽ báo khi có việc mới.
          </Card>
        ) : null}
        {decide.length ? <PendingGroup label="Chị quyết" items={decide} onOpen={setOpen} /> : null}
        {review.length ? <PendingGroup label="Chờ duyệt" items={review} onOpen={setOpen} /> : null}
        {more > 0 ? (
          <Link href="/desk/duyet" className="self-start text-[14px] font-semibold text-accent">
            Xem thêm {more} việc →
          </Link>
        ) : null}
      </section>

      <Card tone="soft" className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <LevelTag level="auto">AI đã tự làm · {data.ai_done.auto_total} việc</LevelTag>
          <Link href="/desk/nhat-ky-ai?ngay=hom-nay" className="shrink-0 text-[14px] font-semibold text-accent">
            Nhật ký →
          </Link>
        </div>
        {data.ai_done.groups.length ? (
          <ul className="flex flex-col">
            {data.ai_done.groups.map((g) => (
              <li key={g.action}>
                <Link
                  href={`/desk/nhat-ky-ai?ngay=hom-nay&action=${encodeURIComponent(g.action)}`}
                  className="flex items-baseline justify-between gap-3 py-1.5 text-[15px] hover:text-accent"
                >
                  <span className="min-w-0">{g.label}</span>
                  <span className="shrink-0 font-semibold tabular-nums">{g.count}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[14px] text-ink-2">Hôm nay AI chưa tự làm việc nào.</p>
        )}
      </Card>

      {stats.length ? (
        <section aria-label="Số liệu hôm nay" className="flex flex-col gap-2">
          <SectionLabel>Số liệu</SectionLabel>
          <div className="grid grid-cols-3 gap-2 md:grid-cols-4">
            {stats.map((s) => (
              <StatTile key={s.key} value={statValue(s)} label={s.label} hint={s.hint ?? undefined} href={s.href ?? undefined} />
            ))}
          </div>
        </section>
      ) : null}

      <ApprovalSheet item={open} open={!!open} onClose={() => setOpen(null)} />
    </div>
  );
}

function PendingGroup({ label, items, onOpen }: { label: string; items: ApprovalItem[]; onOpen: (i: ApprovalItem) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[13px] font-semibold text-ink-2">
        {label} · {items.length}
      </p>
      <ul className="flex flex-col gap-2">
        {items.map((it) => (
          <li key={it.id}>
            <ApprovalRow item={it} onOpen={onOpen} />
          </li>
        ))}
      </ul>
    </div>
  );
}
