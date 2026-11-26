"use client";

import { Check } from "lucide-react";
import Link from "next/link";
import { ImageBox } from "@/components/ui";
import { platformLabel, type CandidateCard } from "@/lib/api/sourcing";
import { cn } from "@/lib/cn";
import { GuidanceNotes } from "./guidance-notes";
import { formatNumber, formatVndCompact } from "@/lib/format";

export const STAGE_LABEL: Record<string, string> = {
  candidate: "Ứng viên",
  sample: "Mua mẫu",
  trial: "Đang thử",
  selected: "Đã chọn",
  rejected: "Đã loại",
};

/** Một ứng viên trong danh sách: ảnh, tên, nguồn, về tay khoảng, điểm, câu «Đáng xem vì…». */
export function CandidateRow({
  c,
  selectable = false,
  selected = false,
  onToggle,
}: {
  c: CandidateCard;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
}) {
  const score = c.score_total ? Math.round(Number(c.score_total)) : c.ai_score;
  const body = (
    <>
      <div className="flex items-start gap-3">
        {selectable ? (
          <span
            aria-hidden
            className={cn(
              "mt-1 grid size-5 shrink-0 place-items-center rounded-sm border",
              selected ? "border-accent bg-accent text-on-accent" : "border-line-strong bg-surface",
            )}
          >
            {selected ? <Check className="size-3.5" /> : null}
          </span>
        ) : null}
        <ImageBox src={c.thumb_url} alt={c.title_vi} className="w-16 shrink-0" placeholder="Chưa có ảnh" referrerPolicy="no-referrer" />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] leading-snug font-semibold [text-wrap:pretty]">{c.title_vi}</p>
          <p className="mt-0.5 text-[13px] text-ink-2">
            {platformLabel(c.source_platform)}
            {c.seller_name ? ` · ${c.seller_name}` : ""}
            {c.review_count ? ` · ${formatNumber(c.review_count)} đánh giá` : ""}
          </p>
          {c.landed_estimate_vnd ? <p className="mt-0.5 text-sm">Về tay khoảng {formatVndCompact(c.landed_estimate_vnd)}</p> : null}
        </div>
        <div className="flex shrink-0 flex-col items-end">
          <span className="font-display text-[26px] leading-none font-bold tabular-nums">{score ?? "—"}</span>
          {c.score_total ? <span className="mt-1 text-[11px] text-auto">đã thẩm định</span> : null}
          {c.stage !== "candidate" ? <span className="mt-1 text-[11px] text-ink-2">{STAGE_LABEL[c.stage]}</span> : null}
        </div>
      </div>
      {c.rank_reason ? <p className="mt-2 text-[13px] text-ink-2 [text-wrap:pretty]">{c.rank_reason}</p> : null}
      {c.guidance ? <GuidanceNotes g={c.guidance} className="mt-1.5" /> : null}
    </>
  );
  const cls = cn(
    "block w-full rounded-md border bg-surface p-4 text-left transition-colors hover:border-ink-3",
    selected ? "border-accent" : "border-line",
  );
  if (selectable)
    return (
      <button type="button" className={cls} aria-pressed={selected} onClick={onToggle}>
        {body}
      </button>
    );
  return (
    <Link href={`/desk/san-hang/ung-vien/${c.id}`} className={cls}>
      {body}
    </Link>
  );
}
