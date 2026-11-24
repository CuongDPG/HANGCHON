"use client";

import { Check, ChevronDown } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, InlineSelect, Input, LevelTag, ScoreBar, notifyError, notifySuccess } from "@/components/ui";
import { useConfirmScore, useSetScore, type Assessment, type ScoreRow } from "@/lib/api/assessment";

const SCORE_OPTIONS = [
  { value: "", label: "Theo điểm AI" },
  ...Array.from({ length: 11 }, (_, i) => ({ value: String(10 - i), label: `${10 - i} / 10` })),
];

function Row({ s, canEdit, candidateId, assessmentId }: { s: ScoreRow; canEdit: boolean; candidateId: string; assessmentId: string }) {
  const [open, setOpen] = useState(false);
  const [score, setScore] = useState(s.owner_score ? String(Math.round(Number(s.owner_score))) : "");
  const [note, setNote] = useState(s.owner_note ?? "");
  const save = useSetScore(candidateId, assessmentId);
  const weight = Number(s.weight);
  const points = s.points ?? 0;
  return (
    <li className="border-b border-line py-2 last:border-b-0">
      <button type="button" className="flex w-full items-center gap-2 text-left" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <ScoreBar label={s.criterion_label} score={Math.round(points)} max={weight} className="flex-1" />
        <ChevronDown className={`size-4 shrink-0 text-ink-3 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {s.owner_score !== null ? (
        <p className="mt-1 text-[12.5px] text-accent">
          Chị sửa: {Math.round(Number(s.owner_score))}/10 (AI chấm {s.ai_score ? Number(s.ai_score).toLocaleString("vi-VN") : "—"}/10)
        </p>
      ) : null}
      {open ? (
        <div className="mt-2 flex flex-col gap-3 rounded-md bg-soft p-3">
          <p className="text-[13px] text-ink-2">
            <span className="font-medium text-ink">Căn cứ của AI:</span> {s.ai_reason ?? "—"}
          </p>
          {s.owner_note ? (
            <p className="text-[13px]">
              <span className="font-medium">Ghi chú của chị:</span> {s.owner_note}
            </p>
          ) : null}
          {canEdit ? (
            <div className="flex flex-col gap-2">
              <InlineSelect label="Điểm của chị (thang 10)" value={score} onChange={setScore} options={SCORE_OPTIONS} />
              <Input label="Vì sao" value={note} onChange={(e) => setNote(e.target.value)} placeholder="vd. mẫu thử bị lỏng ốc" />
              <Button
                size="sm"
                className="self-end"
                loading={save.isPending}
                onClick={() =>
                  save.mutate(
                    { key: s.criterion_key, owner_score: score === "" ? null : Number(score), owner_note: note.trim() || null },
                    { onSuccess: () => notifySuccess("Đã lưu điểm"), onError: notifyError },
                  )
                }
              >
                Lưu dòng này
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/** b4 — Bảy tiêu chí theo khung của chị; AI chấm nháp kèm căn cứ, chị sửa từng dòng rồi duyệt. */
export function ScoreCard({ a, candidateId, canEdit }: { a: Assessment; candidateId: string; canEdit: boolean }) {
  const confirm = useConfirmScore(candidateId, a.id);
  return (
    <Card>
      <CardHeader
        title="Điểm theo khung của chị"
        aside={a.score_status === "confirmed" ? <Badge tone="success" icon={<Check className="size-3.5" />}>Chị đã duyệt</Badge> : <LevelTag level="review" size="sm" />}
      />
      <ul>
        {a.scores.map((s) => (
          <Row key={s.id} s={s} canEdit={canEdit} candidateId={candidateId} assessmentId={a.id} />
        ))}
      </ul>
      {canEdit && a.score_status !== "confirmed" && a.scores.length ? (
        <Button
          variant="secondary"
          block
          className="mt-3"
          icon={<Check className="size-4" />}
          loading={confirm.isPending}
          onClick={() => confirm.mutate(undefined, { onSuccess: () => notifySuccess("Đã duyệt điểm"), onError: notifyError })}
        >
          Duyệt điểm
        </Button>
      ) : null}
    </Card>
  );
}
