"use client";

import { MessageCircleReply, Pencil, Send, X } from "lucide-react";
import { useState } from "react";
import { Button, LevelTag, Textarea, notifySuccess } from "@/components/ui";
import { useDismissDraft, useSendDraft, type ReplyDraft } from "@/lib/api/inbox";
import { cn } from "@/lib/cn";

/**
 * Bản nháp AI trong hội thoại (h2) hoặc việc chuyển chị (h3).
 * - Nháp: «AI soạn» + nút Sửa / Gửi.
 * - Chuyển chị: nhãn đỏ son «AI không tự trả lời», tóm tắt, các phương án AI gợi ý → chị chọn, sửa, gửi.
 */
export function DraftBox({ draft, escalationLabel, compact = false }: { draft: ReplyDraft; escalationLabel?: string | null; compact?: boolean }) {
  const send = useSendDraft();
  const dismiss = useDismissDraft();
  const [editing, setEditing] = useState<string | null>(null);
  const escalation = draft.kind === "escalation";

  async function submit(body?: string) {
    await send.mutateAsync({ draftId: draft.id, body });
    setEditing(null);
    notifySuccess(escalation && !body ? "Đã đánh dấu xử lý xong" : "Đã gửi cho khách");
  }

  if (escalation) {
    return (
      <div className="flex flex-col gap-2">
        <LevelTag level="owner" className="self-start">
          {escalationLabel ?? "Cần chị xem"} · AI không tự trả lời
        </LevelTag>
        <p className="text-[14.5px] text-ink-2 [text-wrap:pretty]">{draft.body}</p>
        {editing !== null ? (
          <Editor value={editing} onChange={setEditing} onCancel={() => setEditing(null)} onSend={() => submit(editing)} loading={send.isPending} />
        ) : (
          <>
            {draft.options.length ? (
              <p className="text-[13px] text-ink-2">
                AI đề xuất: {draft.options.map((o) => o.label.toLowerCase()).join(", hoặc ")}.
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {draft.options.map((o) => (
                <Button key={o.label} size="sm" variant="secondary" onClick={() => setEditing(o.reply)}>
                  {o.label}
                </Button>
              ))}
              <Button size="sm" variant="secondary" icon={<MessageCircleReply className="size-4" />} onClick={() => setEditing("")}>
                Tự trả lời
              </Button>
              {!compact ? (
                <Button size="sm" variant="ghost" loading={send.isPending} onClick={() => submit()}>
                  Đã xử lý xong
                </Button>
              ) : null}
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-md bg-review-wash/60 p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <LevelTag level="review" size="sm">
          AI soạn{draft.kind === "instant" ? " · câu thường gặp" : ""}
        </LevelTag>
        {!compact ? (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[13px] text-ink-2 hover:text-ink"
            onClick={() => dismiss.mutate(draft.id)}
            disabled={dismiss.isPending}
          >
            <X className="size-3.5" aria-hidden /> Bỏ nháp
          </button>
        ) : null}
      </div>
      {editing !== null ? (
        <Editor value={editing} onChange={setEditing} onCancel={() => setEditing(null)} onSend={() => submit(editing)} loading={send.isPending} />
      ) : (
        <>
          <p className={cn("text-[15px] leading-relaxed whitespace-pre-line [text-wrap:pretty]", compact && "line-clamp-4")}>{draft.body}</p>
          {!compact && draft.sources.some((s) => s.fact) ? (
            <p className="mt-1.5 text-[12.5px] text-ink-2">Căn cứ: {draft.sources.map((s) => s.fact).filter(Boolean).join(" · ")}</p>
          ) : null}
          <div className="mt-2.5 flex gap-2">
            <Button size="sm" variant="secondary" icon={<Pencil className="size-4" />} onClick={() => setEditing(draft.body)}>
              Sửa
            </Button>
            <Button size="sm" icon={<Send className="size-4" />} loading={send.isPending} onClick={() => submit()}>
              Gửi
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function Editor({ value, onChange, onCancel, onSend, loading }: {
  value: string;
  onChange: (v: string) => void;
  onCancel: () => void;
  onSend: () => void;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Textarea aria-label="Câu trả lời" value={value} onChange={(e) => onChange(e.target.value)} rows={3} autoFocus />
      <div className="flex gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Huỷ
        </Button>
        <Button size="sm" icon={<Send className="size-4" />} loading={loading} disabled={!value.trim()} onClick={onSend}>
          Gửi
        </Button>
      </div>
    </div>
  );
}
