"use client";

import { useState } from "react";
import { Button, Chip, Sheet, Textarea, notifyError, notifySuccess, useConfirm } from "@/components/ui";
import { useChangeStage, type StageTarget } from "@/lib/api/assessment";
import type { CandidateStage } from "@/lib/api/sourcing";

const REJECT_TAGS = ["Chất lượng kém", "Không an toàn", "Biên thấp", "Giống hàng đang bán", "Nghi hàng nhái", "Cước quá cao"];

/** Loại / Mua mẫu / Chọn — gọi API của Bàn chọn (module selection). Loại phải ghi lý do (c4). */
export function DecisionBar({ candidateId, title, stage }: { candidateId: string; title: string; stage: CandidateStage }) {
  const confirm = useConfirm();
  const change = useChangeStage(candidateId);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");

  function go(to: StageTarget, why?: string, done?: () => void) {
    change.mutate(
      { to, reason: why },
      {
        onSuccess: () => {
          done?.();
          notifySuccess(to === "rejected" ? "Đã loại món này" : to === "sample" ? "Đã chuyển sang Mua mẫu" : "Đã chọn món này");
        },
        onError: notifyError,
      },
    );
  }

  async function ask(to: "sample" | "selected") {
    const ok = await confirm({
      title: to === "sample" ? "Mua mẫu món này?" : "Chọn món này?",
      message:
        to === "sample"
          ? `«${title}» sẽ sang cột Mua mẫu trên Bàn chọn.`
          : `«${title}» sẽ được đóng dấu Đã chọn và AI dựng trang sản phẩm nháp để chị duyệt.`,
      confirmLabel: to === "sample" ? "Mua mẫu" : "Chọn",
    });
    if (ok) go(to);
  }

  const pending = change.isPending;
  return (
    <>
      <div className="sticky bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+72px)] z-10 md:bottom-24">
        <div className="grid grid-cols-3 gap-2 rounded-md border border-line bg-surface p-2 shadow-pop">
          <Button variant="secondary" disabled={pending || stage === "rejected"} onClick={() => setRejectOpen(true)}>
            Loại
          </Button>
          <Button variant="secondary" disabled={pending || stage === "sample"} onClick={() => ask("sample")}>
            Mua mẫu
          </Button>
          <Button disabled={pending || stage === "selected"} loading={pending} onClick={() => ask("selected")}>
            Chọn
          </Button>
        </div>
      </div>
      <Sheet
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        title="Vì sao loại món này?"
        description="Lý do loại được lưu cho trang Hồ sơ chọn và để AI học gu của chị."
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejectOpen(false)}>
              Huỷ
            </Button>
            <Button
              variant="danger"
              disabled={reason.trim().length < 3}
              loading={pending}
              onClick={() => go("rejected", reason.trim(), () => setRejectOpen(false))}
            >
              Loại
            </Button>
          </>
        }
      >
        <div className="mb-3 flex flex-wrap gap-2">
          {REJECT_TAGS.map((t) => (
            <Chip key={t} selected={reason.includes(t)} onClick={() => setReason((r) => (r.includes(t) ? r : r ? `${r}; ${t}` : t))}>
              {t}
            </Chip>
          ))}
        </div>
        <Textarea aria-label="Lý do loại" value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="vd. ốc lỏng sau 2 tuần dùng" />
      </Sheet>
    </>
  );
}
