"use client";

import { CalendarClock, ChevronRight, Search } from "lucide-react";
import { Badge, CardLink, DateTime, EmptyState, SectionLabel, SkeletonList } from "@/components/ui";
import { useBriefs, type Brief, type BriefStatus } from "@/lib/api/sourcing";
import { RunProgress } from "./run-progress";

export const BRIEF_STATUS: Record<BriefStatus, { label: string; tone: "warning" | "accent" | "neutral" | "success" | "outline" }> = {
  draft: { label: "Chờ chị xác nhận", tone: "warning" },
  active: { label: "Đang chạy", tone: "accent" },
  paused: { label: "Tạm dừng", tone: "neutral" },
  done: { label: "Đã chọn được", tone: "success" },
  archived: { label: "Đã cất", tone: "outline" },
};

function BriefItem({ b }: { b: Brief }) {
  const st = BRIEF_STATUS[b.status];
  return (
    <CardLink href={`/desk/san-hang/de/${b.id}`} className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold [text-wrap:pretty]">{b.title}</p>
          <p className="mt-0.5 line-clamp-2 text-[13px] text-ink-2">{b.raw_text}</p>
        </div>
        <ChevronRight className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
        <Badge tone={st.tone}>{st.label}</Badge>
        {b.candidate_count ? <span>{b.candidate_count} ứng viên</span> : null}
        {b.is_scheduled ? (
          <span className="inline-flex items-center gap-1">
            <CalendarClock className="size-3.5" aria-hidden />
            Chạy lại mỗi tuần
          </span>
        ) : null}
        {b.last_run_at ? (
          <span className="text-ink-3">
            · <DateTime value={b.last_run_at} format="relative" />
          </span>
        ) : null}
      </div>
      {b.last_run && (b.last_run.status !== "succeeded" || b.status === "active") ? <RunProgress run={b.last_run} compact /> : null}
    </CardLink>
  );
}

export function BriefList() {
  const { data, isPending, error } = useBriefs();
  return (
    <section className="flex flex-col gap-3" aria-label="Đề tìm">
      <SectionLabel>Đề tìm của chị</SectionLabel>
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được đề tìm" description={error.message} />
      ) : !data.items.length ? (
        <EmptyState icon={<Search />} title="Chưa có đề nào" description="Gõ hoặc nói món chị muốn tìm ở ô phía trên." />
      ) : (
        data.items.map((b) => <BriefItem key={b.id} b={b} />)
      )}
    </section>
  );
}
