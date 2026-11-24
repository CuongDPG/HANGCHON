"use client";

import { FileText, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import {
  Badge,
  Button,
  DateTime,
  IconButton,
  InlineSelect,
  Input,
  Sheet,
  notifySuccess,
  useConfirm,
  type BadgeTone,
} from "@/components/ui";
import {
  DOC_LABELS,
  PO_STATUS_LABELS,
  useDeleteDocument,
  useDocuments,
  useUploadDocument,
  type DocumentKind,
  type POStatus,
} from "@/lib/api/supply";

const PO_TONE: Record<POStatus, BadgeTone> = {
  draft: "outline",
  pending_approval: "warning",
  approved: "accent",
  sent: "accent",
  confirmed: "accent",
  paid: "accent",
  partially_received: "warning",
  received: "success",
  cancelled: "neutral",
};

export function POStatusBadge({ status }: { status: POStatus }) {
  return <Badge tone={PO_TONE[status]}>{PO_STATUS_LABELS[status]}</Badge>;
}

/** Số tiền ngoại tệ: «31 CNY», «1.280 JPY». */
export function moneyAmount(v: string | number, currency: string) {
  return `${Number(v).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} ${currency}`;
}

/** Danh sách chứng từ nguồn gốc (d4) của một đơn hoặc một lô, kèm tải lên. */
export function DocumentsBlock({
  purchaseOrderId,
  inboundId,
  missing,
}: {
  purchaseOrderId?: string;
  inboundId?: string;
  missing: string[];
}) {
  const q = purchaseOrderId ? { purchase_order_id: purchaseOrderId } : { inbound_shipment_id: inboundId };
  const { data } = useDocuments(q);
  const del = useDeleteDocument();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      {missing.length ? (
        <p className="rounded-md bg-review-wash px-3 py-2 text-[14px] text-review">
          Lô này còn thiếu: {missing.map((m) => DOC_LABELS[m as DocumentKind] ?? m).join(", ")}.
        </p>
      ) : null}
      {data?.length ? (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {data.map((d) => (
            <li key={d.id} className="flex items-center gap-3 px-3 py-2">
              <FileText className="size-5 shrink-0 text-ink-3" aria-hidden />
              <div className="min-w-0 flex-1">
                <a href={d.url ?? "#"} target="_blank" rel="noreferrer" className="block truncate text-[15px] font-medium hover:underline">
                  {DOC_LABELS[d.kind]}
                  {d.doc_number ? ` · ${d.doc_number}` : ""}
                </a>
                <p className="truncate text-[13px] text-ink-2">
                  {d.filename} · <DateTime value={d.created_at} format="date" />
                </p>
              </div>
              <IconButton
                size="sm"
                label="Xoá chứng từ"
                icon={<Trash2 />}
                onClick={async () => {
                  if (await confirm({ title: "Xoá chứng từ này?", confirmLabel: "Xoá", tone: "danger" })) {
                    await del.mutateAsync(d.id);
                    notifySuccess("Đã xoá chứng từ");
                  }
                }}
              />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[14px] text-ink-2">Chưa có chứng từ nào.</p>
      )}
      <Button size="sm" variant="secondary" className="self-start" icon={<Upload className="size-4" aria-hidden />} onClick={() => setOpen(true)}>
        Tải chứng từ
      </Button>
      <UploadSheet
        open={open}
        onClose={() => setOpen(false)}
        purchaseOrderId={purchaseOrderId}
        inboundId={inboundId}
        defaultKind={(missing[0] as DocumentKind) ?? "invoice"}
      />
    </div>
  );
}

export function UploadSheet({
  open,
  onClose,
  purchaseOrderId,
  inboundId,
  defaultKind,
}: {
  open: boolean;
  onClose: () => void;
  purchaseOrderId?: string;
  inboundId?: string;
  defaultKind: DocumentKind;
}) {
  return (
    <Sheet open={open} onClose={onClose} title="Tải chứng từ nguồn gốc" description="Ảnh hoặc PDF: hoá đơn, tờ khai, ảnh nhãn gốc…">
      {open ? <UploadForm purchaseOrderId={purchaseOrderId} inboundId={inboundId} defaultKind={defaultKind} onClose={onClose} /> : null}
    </Sheet>
  );
}

function UploadForm({
  purchaseOrderId,
  inboundId,
  defaultKind,
  onClose,
}: {
  purchaseOrderId?: string;
  inboundId?: string;
  defaultKind: DocumentKind;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<DocumentKind>(defaultKind);
  const [file, setFile] = useState<File | null>(null);
  const [num, setNum] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();
  return (
    <div className="flex flex-col gap-4">
      <InlineSelect
        label="Loại chứng từ"
        value={kind}
        onChange={setKind}
        options={(Object.keys(DOC_LABELS) as DocumentKind[]).map((k) => ({ value: k, label: DOC_LABELS[k] }))}
      />
      <Input label="Số chứng từ" value={num} onChange={(e) => setNum(e.target.value)} placeholder="Không bắt buộc" />
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => input.current?.click()}>
          Chọn tệp
        </Button>
        <span className="truncate text-[14px] text-ink-2">{file?.name ?? "Chưa chọn tệp"}</span>
      </div>
      <input ref={input} type="file" accept="image/*,application/pdf" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <div className="flex justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button
          disabled={!file}
          loading={upload.isPending}
          onClick={async () => {
            if (!file) return;
            await upload.mutateAsync({ file, kind, purchase_order_id: purchaseOrderId, inbound_shipment_id: inboundId, doc_number: num || undefined });
            notifySuccess("Đã lưu chứng từ");
            onClose();
          }}
        >
          Lưu chứng từ
        </Button>
      </div>
    </div>
  );
}
