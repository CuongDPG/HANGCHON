"use client";

import { Mic, Trash2 } from "lucide-react";
import { Badge, DateTime, IconButton, ImageBox, useConfirm } from "@/components/ui";
import { POINT_LABELS, useDeleteNote, type PointKind, type TrialNote } from "@/lib/api/selection";

const POINT_TONE: Record<PointKind, "success" | "danger" | "accent"> = { good: "success", bad: "danger", measure: "accent" };

/** Một ghi chú thử hàng: các ý AI đã sắp (gắn nhãn), lời gốc, ảnh, ghi âm. */
export function NoteItem({ note }: { note: TrialNote }) {
  const confirm = useConfirm();
  const del = useDeleteNote();
  return (
    <li className="rounded-md border border-line bg-surface p-3">
      <div className="flex items-center gap-2 text-[13px] text-ink-2">
        {note.author === "tester" ? <Badge tone="accent">Khách thử · {note.author_name ?? "khách quen"}</Badge> : null}
        {note.kind === "voice" ? <Mic className="size-3.5" aria-label="Ghi bằng giọng nói" /> : null}
        <DateTime value={note.recorded_at} format="dateTime" />
        {note.trial_day ? <span>· ngày thử thứ {note.trial_day}</span> : null}
        {note.processing_status === "pending" ? <Badge tone="warning">AI chờ chị duyệt cách sắp</Badge> : null}
        {note.processing_status === "failed" ? <Badge tone="danger">AI chưa sắp được</Badge> : null}
        <IconButton
          size="sm"
          label="Xoá ghi chú"
          icon={<Trash2 />}
          className="ml-auto -mr-1.5 size-8 text-ink-3"
          onClick={async () => {
            if (await confirm({ title: "Xoá ghi chú này?", message: "Ảnh và ghi âm kèm theo cũng bị xoá.", confirmLabel: "Xoá", tone: "danger" })) {
              del.mutate(note.id);
            }
          }}
        />
      </div>
      {note.points.length ? (
        <ul className="mt-2 flex flex-col gap-1.5">
          {note.points.map((p, i) => (
            <li key={i} className="flex items-start gap-2 text-[15px]">
              <Badge tone={POINT_TONE[p.kind]} className="mt-0.5 shrink-0">
                {POINT_LABELS[p.kind]}
              </Badge>
              <span>{p.text}</span>
            </li>
          ))}
        </ul>
      ) : note.text ? (
        <p className="mt-2 text-[15px]">«{note.text}»</p>
      ) : null}
      {note.points.length && note.text ? (
        <details className="mt-2 text-[14px] text-ink-2">
          <summary className="cursor-pointer select-none">Lời gốc</summary>
          <p className="mt-1">«{note.text}»</p>
        </details>
      ) : null}
      {note.photo_urls.length ? (
        <div className="mt-2 grid grid-cols-4 gap-2">
          {note.photo_urls.map((u, i) => (
            <a key={u} href={u} target="_blank" rel="noreferrer">
              <ImageBox src={u} alt={`Ảnh chị chụp ${i + 1}`} />
            </a>
          ))}
        </div>
      ) : null}
      {note.audio_url ? <audio controls preload="none" src={note.audio_url} className="mt-2 h-9 w-full" /> : null}
    </li>
  );
}
