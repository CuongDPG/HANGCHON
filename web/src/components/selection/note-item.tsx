"use client";

import { Globe, Mic, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Checkbox, DateTime, IconButton, ImageBox, Switch, Textarea, notifySuccess, useConfirm } from "@/components/ui";
import { POINT_LABELS, useDeleteNote, useUpdateNote, type PointKind, type TrialNote } from "@/lib/api/selection";

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
        {note.is_public ? <Badge tone="success" icon={<Globe className="size-3" aria-hidden />}>Trên website</Badge> : null}
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
      {note.author === "owner" && note.candidate_id ? <PublicNote note={note} /> : null}
    </li>
  );
}

/** «Ghi chú dùng thử» trên website: chị tích từng ghi chú, sửa lời bản website, chọn kèm ảnh. Soát lời chỉ báo, không chặn. */
function PublicNote({ note }: { note: TrialNote }) {
  const update = useUpdateNote();
  const [text, setText] = useState(note.public_text ?? "");
  const [shown, setShown] = useState(note.public_text);
  if (shown !== note.public_text) {
    // bản lời máy chủ trả về (vd lần đầu tích: lời gốc đã đổi «chị» → «mình») thay cho ô đang sửa
    setShown(note.public_text);
    setText(note.public_text ?? "");
  }
  const dirty = (note.public_text ?? "") !== text.trim();
  return (
    <div className="mt-2 border-t border-line pt-2">
      <Switch
        label="Đưa lên website"
        checked={note.is_public}
        disabled={update.isPending}
        onChange={(v) => update.mutate({ id: note.id, is_public: v }, { onSuccess: () => notifySuccess(v ? "Đã đưa lên website" : "Đã gỡ khỏi website") })}
      />
      {note.is_public ? (
        <div className="mt-2 flex flex-col gap-2">
          <Textarea
            label="Lời trên website"
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {dirty ? (
            <Button
              size="sm"
              variant="secondary"
              className="self-start"
              loading={update.isPending}
              onClick={() => update.mutate({ id: note.id, public_text: text }, { onSuccess: () => notifySuccess("Đã lưu lời trên website") })}
            >
              Lưu lời trên website
            </Button>
          ) : null}
          {note.photo_urls.length ? (
            <Checkbox
              label="Kèm ảnh của ghi chú"
              checked={note.public_photo_urls.length > 0}
              disabled={update.isPending}
              onChange={(e) => update.mutate({ id: note.id, public_photos: e.target.checked })}
            />
          ) : null}
          {note.public_warnings.length ? (
            <ul className="flex flex-col gap-1 rounded-md bg-soft px-3 py-2 text-[13.5px]" aria-label="Soát lời trước khi lên website">
              {note.public_warnings.map((w) => (
                <li key={w} className="flex items-start gap-1.5">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-seal" aria-hidden />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
