"use client";

import { PenLine, RotateCw } from "lucide-react";
import { useState } from "react";
import { Button, Card, Input, LevelTag, Sheet, Textarea, notifySuccess } from "@/components/ui";
import { useApproveReasons, useRedraftReasons, type Decision } from "@/lib/api/selection";

/** «Vì sao mình chọn» + «Điều mình chưa ưng» (c3): AI soạn từ ghi chú, chị sửa lời rồi chốt. */
export function ReasonsCard({ decision }: { decision: Decision }) {
  const [open, setOpen] = useState(false);
  const approved = decision.draft_status === "approved";
  const reasons = approved ? decision.reasons_list : decision.draft_reasons_list;
  const notOk = approved ? decision.not_satisfied_list : decision.draft_not_satisfied_list;
  const redraft = useRedraftReasons();

  return (
    <Card tone="soft" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        {approved ? <LevelTag level="owner">Chị đã chốt lời</LevelTag> : <LevelTag level="review">AI soạn từ ghi chú</LevelTag>}
        {decision.trial_days ? <span className="text-[13px] text-ink-2">Đã thử {decision.trial_days} ngày</span> : null}
      </div>
      <div>
        <h3 className="text-[15px] font-semibold">Vì sao mình chọn</h3>
        {reasons.length ? (
          <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-5 text-[15px]">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[14px] text-ink-2">Chưa có ghi chú thử nào để AI soạn. Chị tự viết vài ý nhé.</p>
        )}
      </div>
      <div>
        <h3 className="text-[15px] font-semibold">Điều mình chưa ưng</h3>
        {notOk.length ? (
          <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-5 text-[15px]">
            {notOk.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[14px] text-ink-2">Ghi chú chưa nhắc điều gì chưa ưng.</p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" icon={<PenLine className="size-4" aria-hidden />} onClick={() => setOpen(true)}>
          {approved ? "Sửa lời" : "Sửa lời rồi chốt"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          loading={redraft.isPending}
          icon={<RotateCw className="size-4" aria-hidden />}
          onClick={async () => {
            await redraft.mutateAsync({ id: decision.id });
            notifySuccess("AI đã soạn lại từ ghi chú");
          }}
        >
          AI soạn lại
        </Button>
      </div>
      <ReasonsSheet decision={decision} open={open} onClose={() => setOpen(false)} initial={{ reasons, notOk }} />
    </Card>
  );
}

function pad(list: string[], n: number) {
  return [...list, ...Array(Math.max(0, n - list.length)).fill("")].slice(0, Math.max(n, list.length));
}

function ReasonsSheet({
  decision,
  open,
  onClose,
  initial,
}: {
  decision: Decision;
  open: boolean;
  onClose: () => void;
  initial: { reasons: string[]; notOk: string[] };
}) {
  return (
    <Sheet open={open} onClose={onClose} title="Sửa lời của chị" description="Lời này hiện trên trang sản phẩm. Chỉ giữ điều chị đã thật sự thấy.">
      {open ? <ReasonsForm key={decision.id + decision.draft_status} decision={decision} initial={initial} onClose={onClose} /> : null}
    </Sheet>
  );
}

function ReasonsForm({ decision, initial, onClose }: { decision: Decision; initial: { reasons: string[]; notOk: string[] }; onClose: () => void }) {
  const [reasons, setReasons] = useState(() => pad(initial.reasons, 3));
  const [notOk, setNotOk] = useState(() => pad(initial.notOk, 1));
  const [note, setNote] = useState("");
  const approve = useApproveReasons();
  const redraft = useRedraftReasons();
  const filled = reasons.filter((r) => r.trim());

  return (
    <div className="flex flex-col gap-4">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Vì sao mình chọn (tối đa 3 ý)</legend>
        {reasons.map((r, i) => (
          <Input
            key={i}
            aria-label={`Ý ${i + 1}`}
            value={r}
            placeholder={`Ý ${i + 1}`}
            onChange={(e) => setReasons((xs) => xs.map((x, j) => (j === i ? e.target.value : x)))}
          />
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Điều mình chưa ưng</legend>
        {notOk.map((r, i) => (
          <Input
            key={i}
            aria-label={`Điều chưa ưng ${i + 1}`}
            value={r}
            placeholder="Ví dụ: đầu kẹp hơi sắc"
            onChange={(e) => setNotOk((xs) => xs.map((x, j) => (j === i ? e.target.value : x)))}
          />
        ))}
        {notOk.length < 3 ? (
          <Button size="sm" variant="ghost" className="self-start" onClick={() => setNotOk((xs) => [...xs, ""])}>
            + Thêm một điều
          </Button>
        ) : null}
      </fieldset>
      <details className="rounded-md border border-line p-3">
        <summary className="cursor-pointer text-sm font-medium">Nhờ AI soạn lại theo lời nhắn</summary>
        <div className="mt-3 flex flex-col gap-2">
          <Textarea aria-label="Lời nhắn cho AI" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ví dụ: ngắn hơn, nói về độ chắc trước" rows={2} />
          <Button
            size="sm"
            variant="secondary"
            className="self-start"
            loading={redraft.isPending}
            onClick={async () => {
              const d = await redraft.mutateAsync({ id: decision.id, note: note || undefined });
              setReasons(pad(d.draft_reasons_list, 3));
              setNotOk(pad(d.draft_not_satisfied_list, 1));
              notifySuccess("AI đã soạn lại, chị xem rồi chốt");
            }}
          >
            Soạn lại
          </Button>
        </div>
      </details>
      <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Để sau
        </Button>
        <Button
          disabled={!filled.length}
          loading={approve.isPending}
          onClick={async () => {
            await approve.mutateAsync({ id: decision.id, reason_selected: filled, not_satisfied: notOk.filter((r) => r.trim()) });
            notifySuccess("Đã chốt lời cho trang sản phẩm");
            onClose();
          }}
        >
          Chốt lời
        </Button>
      </div>
    </div>
  );
}
