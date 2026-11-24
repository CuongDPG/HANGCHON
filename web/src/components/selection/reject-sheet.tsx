"use client";

import { useState } from "react";
import { Button, Chip, ChipRow, Sheet, Textarea, notifySuccess } from "@/components/ui";
import { useMoveStage, useRejectReasons, type StageChangeResult } from "@/lib/api/selection";

/** Loại một món (c4): lý do bắt buộc, chọn nhanh lý do hay dùng, gắn nhóm để thống kê trên trang Hồ sơ chọn. */
export function RejectSheet({
  candidate,
  onClose,
  onDone,
}: {
  candidate: { id: string; title: string } | null;
  onClose: () => void;
  onDone?: (r: StageChangeResult) => void;
}) {
  return (
    <Sheet open={!!candidate} onClose={onClose} title="Loại món này" description={candidate?.title}>
      {candidate ? <RejectForm key={candidate.id} candidateId={candidate.id} onClose={onClose} onDone={onDone} /> : null}
    </Sheet>
  );
}

function RejectForm({ candidateId, onClose, onDone }: { candidateId: string; onClose: () => void; onDone?: (r: StageChangeResult) => void }) {
  const reasons = useRejectReasons();
  const move = useMoveStage();
  const [text, setText] = useState("");
  const [groups, setGroups] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  function toggle(key: string) {
    setGroups((g) => (g.includes(key) ? g.filter((x) => x !== key) : [...g, key].slice(-2)));
  }

  async function submit() {
    if (text.trim().length < 2) {
      setError("Chị ghi vài chữ vì sao loại nhé.");
      return;
    }
    const r = await move.mutateAsync({ id: candidateId, to: "rejected", reason: text.trim(), reason_tags: groups.length ? groups : undefined });
    notifySuccess("Đã loại, lý do được lưu cho trang Hồ sơ chọn");
    onDone?.(r);
    onClose();
  }

  return (
    <div className="flex flex-col gap-4">
      {reasons.data?.frequent.length ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Lý do hay dùng</p>
          <ChipRow>
            {reasons.data.frequent.map((f) => (
              <Chip
                key={f.text}
                selected={text === f.text}
                onClick={() => {
                  setText(f.text);
                  setGroups([f.group]);
                  setError(null);
                }}
              >
                {f.text}
              </Chip>
            ))}
          </ChipRow>
        </div>
      ) : null}
      <Textarea
        label="Vì sao loại?"
        required
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
        }}
        placeholder="Ví dụ: rò nước ở nắp sau ba ngày dùng"
        error={error}
        rows={3}
      />
      {reasons.data ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">
            Nhóm lý do <span className="font-normal text-ink-2">(để thống kê, chọn tối đa 2; bỏ trống thì AI tự xếp)</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {reasons.data.groups.map((g) => (
              <Chip key={g.key} selected={groups.includes(g.key)} onClick={() => toggle(g.key)}>
                {g.label}
              </Chip>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Để sau
        </Button>
        <Button variant="danger" loading={move.isPending} onClick={submit}>
          Loại món này
        </Button>
      </div>
    </div>
  );
}
