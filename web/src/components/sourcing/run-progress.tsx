"use client";

import { AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import Link from "next/link";
import { ProgressBar, Spinner } from "@/components/ui";
import { isRunActive, type SourcingRun } from "@/lib/api/sourcing";
import { formatNumber } from "@/lib/format";

/** Một dòng tiến độ của lượt tìm (quét đề, lấy link, tìm ảnh…). */
export function RunProgress({ run, compact = false }: { run: SourcingRun; compact?: boolean }) {
  const p = run.progress ?? {};
  const active = isRunActive(run);
  if (active) {
    const total = p.total || 0;
    return (
      <div className="flex flex-col gap-2" role="status">
        <p className="flex items-center gap-2 text-sm text-ink-2">
          <Spinner className="size-4" />
          {p.note || "AI đang tìm…"}
        </p>
        {total > 0 ? <ProgressBar value={p.done ?? 0} max={total} size="sm" label={`Đã quét ${p.done ?? 0} trên ${total} nguồn`} /> : null}
      </div>
    );
  }
  if (run.status === "failed") {
    return (
      <p className="flex items-start gap-2 text-sm text-seal">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>{run.error || p.note || "Lượt tìm bị lỗi."}</span>
      </p>
    );
  }
  if (p.step === "pending" || p.step === "blocked") {
    return (
      <p className="flex items-start gap-2 text-sm text-review">
        <Clock className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          {p.note}{" "}
          {p.step === "pending" ? (
            <Link href="/desk/duyet" className="font-semibold underline underline-offset-2">
              Xem việc chờ duyệt
            </Link>
          ) : null}
        </span>
      </p>
    );
  }
  const sources = run.platforms?.length || run.progress?.total || 0;
  return (
    <p className="flex items-start gap-2 text-sm text-ink-2">
      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-auto" aria-hidden />
      <span>
        {run.kind === "brief_scan" || run.kind === "scheduled_scan" || run.kind === "image_search"
          ? `Đã quét ${sources} nguồn · ${formatNumber(run.found_count)} món · ${formatNumber(run.above_threshold_count)} món đạt tiêu chí`
          : p.note || "Xong"}
        {!compact && run.new_count > 0 && (run.kind === "brief_scan" || run.kind === "scheduled_scan") ? ` · ${run.new_count} món mới` : ""}
        {p.elsewhere_ids?.length ? ` · ${p.elsewhere_ids.length} món đã có ở đề khác` : ""}
      </span>
    </p>
  );
}
