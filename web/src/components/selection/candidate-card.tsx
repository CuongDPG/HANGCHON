"use client";

import { MessageSquareText } from "lucide-react";
import Link from "next/link";
import type { DragEvent } from "react";
import { Badge, ImageBox, Money, ProgressBar, Seal } from "@/components/ui";
import { cn } from "@/lib/cn";
import { PLATFORM_LABELS, type BoardCard } from "@/lib/api/selection";

/** Thẻ một món trên bảng chọn (c1): ảnh, nguồn, tiến độ ngày thử, ghi chú gần nhất, lý do chọn/loại. */
export function CandidateCard({
  card,
  draggable = false,
  onDragStart,
  dragging = false,
  compact = false,
}: {
  card: BoardCard;
  draggable?: boolean;
  onDragStart?: (e: DragEvent<HTMLAnchorElement>) => void;
  dragging?: boolean;
  /** Kanban trên máy tính: bỏ ảnh, chữ gọn. */
  compact?: boolean;
}) {
  const meta = [PLATFORM_LABELS[card.source_platform] ?? card.source_platform, card.ai_score !== null ? `điểm ${card.ai_score}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <Link
      href={`/desk/ban-chon/${card.id}`}
      draggable={draggable}
      onDragStart={onDragStart}
      data-card-id={card.id}
      className={cn(
        "block rounded-md border border-line bg-surface transition-[border-color,opacity] hover:border-ink-3",
        compact ? "p-2.5" : "p-3",
        dragging && "opacity-40",
        draggable && "cursor-grab active:cursor-grabbing",
      )}
    >
      <div className="flex gap-3">
        {compact ? null : <ImageBox src={card.image_url} alt="" ratio="1/1" className="size-14 shrink-0" placeholder="" />}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <h3 className={cn("line-clamp-2 min-w-0 flex-1 leading-snug font-semibold", compact ? "text-[14px]" : "text-[15px]")}>
              {card.title}
            </h3>
            {card.stage === "selected" ? (
              <Seal chosen={card.seal?.chosen} total={card.seal?.total} size={compact ? 34 : 40} className="-mt-1 -mr-1" />
            ) : null}
          </div>
          <p className={cn("mt-0.5 text-[13px] text-ink-2", compact ? "line-clamp-2" : "truncate")}>
            {meta}
            {card.landed_cost_vnd ? (
              <>
                {" · về tay "}
                <Money value={card.landed_cost_vnd} compact />
              </>
            ) : card.price_vnd_estimate ? (
              <>
                {" · ≈ "}
                <Money value={card.price_vnd_estimate} compact />
              </>
            ) : null}
          </p>
        </div>
      </div>

      {card.stage === "trial" && card.trial_day !== null ? (
        <div className="mt-3">
          <p className="mb-1.5 text-[13px] text-ink-2">
            Ngày thử thứ <span className="font-semibold text-ink tabular-nums">{Math.min(card.trial_day, 999)}</span> trong{" "}
            {card.trial_days}
            {card.trial_day > card.trial_days ? <span className="text-review"> · quá hạn thử</span> : null}
          </p>
          <ProgressBar
            value={Math.min(card.trial_day, card.trial_days)}
            max={card.trial_days}
            size="sm"
            tone={card.trial_day >= card.trial_days ? "warning" : "accent"}
            label={`Ngày thử thứ ${card.trial_day} trong ${card.trial_days}`}
          />
        </div>
      ) : null}

      {card.stage === "rejected" && card.decision_summary ? (
        <p className="mt-2 line-clamp-2 text-[14px] text-ink-2">
          <span className="font-medium text-seal">Loại: </span>
          {card.decision_summary}
        </p>
      ) : null}
      {card.stage === "selected" ? (
        card.draft_status === "approved" && card.decision_summary ? (
          <p className="mt-2 line-clamp-2 text-[14px] text-ink-2">«{card.decision_summary}»</p>
        ) : (
          <div className="mt-2">
            <Badge tone="warning" className="h-auto py-0.5 whitespace-normal">
              {compact ? "Chờ chị sửa lời" : "Chờ chị sửa lời «Vì sao mình chọn»"}
            </Badge>
          </div>
        )
      ) : null}

      {card.last_note && (card.stage === "trial" || card.stage === "sample") ? (
        <p className="mt-2 flex gap-1.5 text-[14px] text-ink-2">
          <MessageSquareText className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
          <span className="line-clamp-2">
            «{card.last_note}»<span className="text-ink-3"> · {card.note_count} ghi chú</span>
          </span>
        </p>
      ) : null}
    </Link>
  );
}
