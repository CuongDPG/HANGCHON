"use client";

import { Badge, DateTime, LevelTag } from "@/components/ui";
import type { ApprovalItem } from "@/lib/api/control";
import { cn } from "@/lib/cn";
import { STATUS_LABELS } from "./approval-sheet";

/** Một việc chờ chị: nhãn mức, lời gọi hành động, tiêu đề. Bấm để mở sheet xử lý ngay. */
export function ApprovalRow({ item, onOpen, className }: { item: ApprovalItem; onOpen: (item: ApprovalItem) => void; className?: string }) {
  const pending = item.status === "pending";
  const status = STATUS_LABELS[item.status];
  return (
    <button
      type="button"
      onClick={() => onOpen(item)}
      className={cn(
        "flex w-full flex-col gap-1.5 rounded-md border border-line bg-surface p-3.5 text-left transition-colors hover:border-ink-3",
        item.locked && pending && "border-l-[3px] border-l-seal",
        className,
      )}
    >
      <span className="flex w-full items-center justify-between gap-3">
        <LevelTag level={item.locked ? "owner" : "review"} size="sm">
          {item.locked ? "Chị quyết" : "Chờ duyệt"}
        </LevelTag>
        {pending ? (
          <span className="shrink-0 text-[14px] font-semibold text-accent">{item.locked ? "Xử lý →" : "Duyệt →"}</span>
        ) : status ? (
          <Badge tone={status.tone}>{status.label}</Badge>
        ) : null}
      </span>
      <span className="text-[15px] leading-snug font-semibold [text-wrap:pretty]">{item.title}</span>
      {item.summary ? <span className="line-clamp-2 text-[14px] text-ink-2">{item.summary}</span> : null}
      <span className="text-[12.5px] text-ink-3">
        {item.action_label} · <DateTime value={pending ? item.created_at : item.updated_at} format="relative" />
      </span>
    </button>
  );
}
