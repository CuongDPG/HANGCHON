"use client";

import { ExternalLink, RefreshCw, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, Button, Card, EmptyState, ImageBox, SectionLabel, SkeletonList, notifyError } from "@/components/ui";
import { platformLabel, useDismissTrend, useRefreshTrends, useRun, useTrendBrief, useTrends, type Trend } from "@/lib/api/sourcing";
import { useQueryClient } from "@tanstack/react-query";
import { RunProgress } from "./run-progress";

function TrendItem({ t }: { t: Trend }) {
  const router = useRouter();
  const open = useTrendBrief();
  const dismiss = useDismissTrend();
  return (
    <Card className="flex gap-3">
      <ImageBox src={t.image_url} alt={t.title_vi} className="w-16 shrink-0 self-start" placeholder="" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[15px] font-semibold">{t.title_vi}</p>
          {t.status === "watching" ? <Badge tone="accent">Đã mở đề</Badge> : null}
          {t.status === "converted" ? <Badge tone="success">Có ứng viên</Badge> : null}
        </div>
        <p className="text-[13px] text-ink-2">
          {platformLabel(t.platform)}
          {t.metrics.growth_pct ? ` · tăng ${Math.round(t.metrics.growth_pct)}%` : ""}
          {t.score !== null ? ` · ${t.score} điểm` : ""}
        </p>
        {t.reason ? <p className="text-sm">Đáng xem vì: {t.reason}</p> : null}
        <div className="mt-1 flex flex-wrap gap-2">
          {t.brief_id ? (
            <Button size="sm" variant="secondary" onClick={() => router.push(`/desk/san-hang/de/${t.brief_id}`)}>
              Xem đề tìm
            </Button>
          ) : (
            <Button
              size="sm"
              loading={open.isPending}
              onClick={() => open.mutate(t.id, { onSuccess: (b) => router.push(`/desk/san-hang/de/${b.id}`), onError: notifyError })}
            >
              Mở đề tìm từ tín hiệu này
            </Button>
          )}
          <Button size="sm" variant="ghost" loading={dismiss.isPending} onClick={() => dismiss.mutate(t.id)}>
            Bỏ qua
          </Button>
          <a href={t.url} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-1 px-2 text-sm text-ink-2 hover:text-ink">
            <ExternalLink className="size-3.5" aria-hidden /> Nguồn
          </a>
        </div>
      </div>
    </Card>
  );
}

/** a5 — Radar xu hướng: mỗi sáng 7:00 AI thu tín hiệu; chị bấm «Quét lại» để chạy ngay. */
export function TrendsPanel() {
  const qc = useQueryClient();
  const { data, isPending, error } = useTrends();
  const refresh = useRefreshTrends();
  const [runId, setRunId] = useState<string | null>(null);
  const run = useRun(runId);
  useEffect(() => {
    if (run.data && run.data.status !== "queued" && run.data.status !== "running") qc.invalidateQueries({ queryKey: ["sourcing", "trends"] });
  }, [run.data, qc]);

  return (
    <section className="flex flex-col gap-3" aria-label="Radar xu hướng">
      <SectionLabel
        aside={
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className="size-4" />}
            loading={refresh.isPending}
            onClick={() => refresh.mutate(undefined, { onSuccess: (r) => setRunId(r.id), onError: notifyError })}
          >
            Quét lại
          </Button>
        }
      >
        Đang lên tuần này
      </SectionLabel>
      <p className="-mt-1 text-[13px] text-ink-2">Tiểu Hồng Thư, @cosme, TikTok Shop Việt Nam. AI tự quét lúc 7 giờ mỗi sáng.</p>
      {run.data ? <RunProgress run={run.data} /> : null}
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được tín hiệu" description={error.message} />
      ) : !data.items.length ? (
        <EmptyState icon={<TrendingUp />} title="Chưa có tín hiệu nào" description="Bấm «Quét lại» để AI thu tín hiệu ngay." />
      ) : (
        data.items.map((t) => <TrendItem key={t.id} t={t} />)
      )}
    </section>
  );
}
