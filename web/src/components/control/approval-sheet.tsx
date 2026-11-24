"use client";

import { Check, CornerUpLeft, PencilLine } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, DateTime, Input, LevelTag, Sheet, Skeleton, Textarea, notifySuccess } from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useApproval, useApprove, useReturnApproval, type ApprovalItem } from "@/lib/api/control";
import { PreviewView, Rationale } from "./preview-view";

export const STATUS_LABELS: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "danger" | "outline" }> = {
  pending: { label: "Đang chờ", tone: "warning" },
  approved: { label: "Đã duyệt", tone: "success" },
  returned: { label: "Đã trả lại", tone: "neutral" },
  failed: { label: "Duyệt nhưng lỗi", tone: "danger" },
  cancelled: { label: "Đã huỷ", tone: "outline" },
  expired: { label: "Quá hạn", tone: "outline" },
};

/** Trường sửa được: chuỗi/số ở tầng trên cùng của payload, trừ mã định danh. */
function editableFields(payload: Record<string, unknown>) {
  return Object.entries(payload).filter(
    ([k, v]) => (typeof v === "string" || typeof v === "number") && k !== "id" && !k.endsWith("_id") && !k.endsWith("_key"),
  ) as [string, string | number][];
}

const FIELD_LABELS: Record<string, string> = {
  text: "Nội dung",
  title: "Tiêu đề",
  body: "Nội dung",
  price_vnd: "Giá (đ)",
  buyer_name: "Người mua",
  buyer_tax_code: "Mã số thuế",
  buyer_address: "Địa chỉ",
  buyer_email: "Email nhận hoá đơn",
  summary: "Tóm tắt",
  plan: "Phương án",
  channel: "Kênh",
  scheduled: "Giờ đăng",
  note: "Ghi chú",
};

type Mode = "view" | "edit" | "return";

/**
 * Xem trước và quyết một việc chờ duyệt (i2): duyệt · sửa rồi duyệt · trả lại kèm lời nhắn.
 * Truyền `item` (đã có sẵn trong danh sách) hoặc chỉ `itemId` (tự tải).
 */
export function ApprovalSheet({
  item: given,
  itemId,
  open,
  onClose,
  onDone,
}: {
  item?: ApprovalItem | null;
  itemId?: string | null;
  open: boolean;
  onClose: () => void;
  onDone?: (item: ApprovalItem) => void;
}) {
  const fetched = useApproval(given ? null : (itemId ?? null));
  const item = given ?? fetched.data ?? null;
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={item?.title ?? "Việc chờ duyệt"}
      description={item?.summary ?? undefined}
    >
      {item ? (
        <ApprovalBody key={item.id + item.updated_at} item={item} onClose={onClose} onDone={onDone} />
      ) : fetched.isError ? (
        <p className="text-[15px] text-seal">{fetched.error.message}</p>
      ) : (
        <div className="flex flex-col gap-3" role="status" aria-label="Đang tải">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-28 w-full" />
        </div>
      )}
    </Sheet>
  );
}

function ApprovalBody({ item, onClose, onDone }: { item: ApprovalItem; onClose: () => void; onDone?: (item: ApprovalItem) => void }) {
  const { user } = useSession();
  const owner = isOwner(user);
  const [mode, setMode] = useState<Mode>("view");
  const fields = editableFields(item.payload);
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(fields.map(([k, v]) => [k, String(v)])));
  const [note, setNote] = useState("");
  const approve = useApprove();
  const giveBack = useReturnApproval();
  const decidable = item.status === "pending" || item.status === "failed";
  const status = STATUS_LABELS[item.status];

  function changed(): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const [k, v] of fields) {
      const next = draft[k] ?? "";
      if (next === String(v)) continue;
      out[k] = typeof v === "number" ? Number(next.replace(/\D/g, "")) || 0 : next;
    }
    return out;
  }

  async function doApprove(edited?: Record<string, unknown>) {
    const res = await approve.mutateAsync({ id: item.id, payload: edited && Object.keys(edited).length ? edited : undefined });
    if (res.status === "failed") return; // lỗi thực thi: ở lại xem lỗi, duyệt lại được
    notifySuccess(edited && Object.keys(edited).length ? "Đã sửa và duyệt" : "Đã duyệt");
    onDone?.(res);
    onClose();
  }

  async function doReturn() {
    const res = await giveBack.mutateAsync({ id: item.id, note: note.trim() });
    notifySuccess("Đã trả lại cho AI kèm lời nhắn");
    onDone?.(res);
    onClose();
  }

  const busy = approve.isPending || giveBack.isPending;
  const latest = approve.data?.id === item.id ? approve.data : item;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <LevelTag level={item.locked ? "owner" : "review"} size="sm">
          {item.locked ? "Chị quyết" : "Chờ duyệt"}
        </LevelTag>
        <span className="text-[13px] text-ink-2">{item.action_label}</span>
        <span className="text-[13px] text-ink-3">
          · <DateTime value={item.created_at} format="relative" />
        </span>
        {item.status !== "pending" && status ? <Badge tone={status.tone}>{status.label}</Badge> : null}
        {item.href ? (
          <Link href={item.href} className="ml-auto text-[14px] font-semibold text-accent" onClick={onClose}>
            Mở chi tiết →
          </Link>
        ) : null}
      </div>

      {latest.error ? (
        <p role="alert" className="rounded-md bg-seal-wash p-3 text-[14px] text-seal">
          Lần duyệt trước thực thi lỗi: {latest.error}. Chị duyệt lại được.
        </p>
      ) : null}

      {mode === "edit" ? (
        <div className="flex flex-col gap-3">
          {fields.map(([k, v]) =>
            typeof v === "string" && (v.length > 60 || v.includes("\n")) ? (
              <Textarea key={k} label={FIELD_LABELS[k] ?? k} value={draft[k] ?? ""} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} rows={6} />
            ) : (
              <Input
                key={k}
                label={FIELD_LABELS[k] ?? k}
                value={draft[k] ?? ""}
                inputMode={typeof v === "number" ? "numeric" : undefined}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              />
            ),
          )}
        </div>
      ) : (
        <PreviewView preview={item.preview} />
      )}

      {mode === "return" ? (
        <Textarea
          label="Lời nhắn cho AI"
          placeholder="Vd: bỏ câu «tốt nhất», thêm điều chưa ưng về nắp"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          autoFocus
        />
      ) : null}

      {mode === "view" ? <Rationale rationale={item.rationale} sources={item.sources} /> : null}

      {item.decision_note && item.status !== "pending" ? (
        <p className="text-[14px] text-ink-2">
          <span className="font-semibold text-ink">Lời nhắn: </span>
          {item.decision_note}
        </p>
      ) : null}

      {decidable && !owner ? <p className="text-[14px] text-ink-2">Chỉ chị (chủ cửa hàng) duyệt được việc này.</p> : null}

      {decidable && owner ? (
        <div className="sticky bottom-0 -mx-5 -mb-5 flex flex-wrap gap-2 border-t border-line bg-surface px-5 py-3 [&>*]:flex-1">
          {mode === "view" ? (
            <>
              <Button variant="secondary" icon={<CornerUpLeft className="size-4" />} onClick={() => setMode("return")} disabled={busy}>
                Trả lại
              </Button>
              {fields.length ? (
                <Button variant="secondary" icon={<PencilLine className="size-4" />} onClick={() => setMode("edit")} disabled={busy}>
                  Sửa
                </Button>
              ) : null}
              <Button icon={<Check className="size-4" />} loading={approve.isPending} onClick={() => doApprove()}>
                Duyệt
              </Button>
            </>
          ) : mode === "edit" ? (
            <>
              <Button variant="secondary" onClick={() => setMode("view")} disabled={busy}>
                Thôi sửa
              </Button>
              <Button icon={<Check className="size-4" />} loading={approve.isPending} onClick={() => doApprove(changed())}>
                Duyệt bản đã sửa
              </Button>
            </>
          ) : (
            <>
              <Button variant="secondary" onClick={() => setMode("view")} disabled={busy}>
                Thôi
              </Button>
              <Button loading={giveBack.isPending} disabled={!note.trim()} onClick={doReturn}>
                Gửi lời nhắn
              </Button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
