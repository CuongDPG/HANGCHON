"use client";

import { FileText, Pencil, RotateCcw, Sparkles, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import {
  Badge,
  Button,
  DateTime,
  IconButton,
  InlineSelect,
  Input,
  Sheet,
  Spinner,
  notifySuccess,
  useConfirm,
  type BadgeTone,
} from "@/components/ui";
import {
  DOC_LABELS,
  EXTRACT_LABELS,
  PO_STATUS_LABELS,
  useDeleteDocument,
  useDocuments,
  useEditDocument,
  useRereadDocument,
  useUploadDocument,
  type DocumentKind,
  type ExtractField,
  type POStatus,
  type ProvenanceDoc,
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
  const [editing, setEditing] = useState<ProvenanceDoc | null>(null);
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
            <li key={d.id} className="flex flex-col gap-2 px-3 py-2">
              <div className="flex items-center gap-3">
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
              </div>
              <DocExtractPanel doc={d} onEdit={() => setEditing(d)} />
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
      <Sheet open={!!editing} onClose={() => setEditing(null)} title="Thông tin chứng từ" description="AI đọc sẵn; chị sửa cho đúng với giấy tờ.">
        {editing ? <ExtractForm doc={editing} onClose={() => setEditing(null)} /> : null}
      </Sheet>
    </div>
  );
}

const STATUS_TEXT: Record<string, string> = {
  pending: "Phần AI đọc đang chờ chị duyệt trong hàng chờ.",
  failed: "AI chưa đọc được chứng từ này.",
  unreadable: "Không lấy được chữ hay ảnh từ tệp này.",
  off: "Chị đang tắt việc AI đọc chứng từ.",
};

/** Phần AI đọc từ chứng từ (d4): tên hàng, nhà sản xuất, xuất xứ, số lô, ngày, chứng nhận. Chị sửa, đọc lại được. */
function DocExtractPanel({ doc, onEdit }: { doc: ProvenanceDoc; onEdit: () => void }) {
  const reread = useRereadDocument();
  const ex = doc.extracted ?? {};
  if (!ex.status) return null;
  if (ex.status === "reading") {
    return (
      <p className="flex items-center gap-2 pl-8 text-[13.5px] text-ink-2">
        <Spinner className="size-4" /> AI đang đọc chứng từ…
      </p>
    );
  }
  const fields = (Object.keys(EXTRACT_LABELS) as ExtractField[]).filter((k) => ex[k]);
  const dates = [ex.doc_date && `Ngày chứng từ ${ex.doc_date}`].filter(Boolean);
  const again = (
    <Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" aria-hidden />} loading={reread.isPending} onClick={() => reread.mutate(doc.id, { onSuccess: () => notifySuccess("Đã gửi AI đọc lại") })}>
      Đọc lại
    </Button>
  );
  if (ex.status !== "read") {
    return (
      <div className="ml-8 flex flex-wrap items-center gap-2 rounded-md bg-soft px-3 py-2 text-[13.5px] text-ink-2">
        <span className="min-w-0 flex-1">{ex.note ?? STATUS_TEXT[ex.status] ?? ""}</span>
        {ex.status !== "pending" ? again : null}
        <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" aria-hidden />} onClick={onEdit}>
          Nhập tay
        </Button>
      </div>
    );
  }
  return (
    <div className="ml-8 flex flex-col gap-1.5 rounded-md bg-soft px-3 py-2">
      <p className="flex flex-wrap items-center gap-1.5 text-[13px] font-semibold text-ink-2">
        <Sparkles className="size-3.5 text-accent" aria-hidden /> AI đọc
        {ex.edited ? <Badge tone="outline">Chị đã sửa</Badge> : null}
        {ex.readable === false ? <Badge tone="warning">Ảnh mờ, chị kiểm lại</Badge> : null}
      </p>
      {ex.summary ? <p className="text-[14px]">{ex.summary}</p> : null}
      {fields.length || dates.length ? (
        <dl className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-[13.5px] sm:grid-cols-2">
          {fields.map((k) => (
            <div key={k} className="flex gap-1.5">
              <dt className="shrink-0 text-ink-2">{EXTRACT_LABELS[k]}:</dt>
              <dd className="min-w-0 break-words">{ex[k]}</dd>
            </div>
          ))}
          {dates.map((t) => (
            <div key={t as string} className="text-ink-2">
              {t}
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-[13.5px] text-ink-2">Chưa thấy trường nào rõ trên chứng từ.</p>
      )}
      {ex.certifications?.length ? (
        <ul className="flex flex-wrap gap-1.5">
          {ex.certifications.map((c) => (
            <li key={c} className="rounded-sm bg-surface px-2 py-0.5 text-[12.5px]">
              {c}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap gap-1">
        <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" aria-hidden />} onClick={onEdit}>
          Sửa
        </Button>
        {again}
      </div>
    </div>
  );
}

function ExtractForm({ doc, onClose }: { doc: ProvenanceDoc; onClose: () => void }) {
  const edit = useEditDocument();
  const ex = doc.extracted ?? {};
  const [form, setForm] = useState<Record<ExtractField, string>>(
    () => Object.fromEntries((Object.keys(EXTRACT_LABELS) as ExtractField[]).map((k) => [k, ex[k] ?? ""])) as Record<ExtractField, string>,
  );
  const [num, setNum] = useState(doc.doc_number ?? "");
  const [certs, setCerts] = useState((ex.certifications ?? []).join(", "));
  return (
    <div className="flex flex-col gap-3">
      <Input label="Số chứng từ" value={num} onChange={(e) => setNum(e.target.value)} />
      {(Object.keys(EXTRACT_LABELS) as ExtractField[]).map((k) => (
        <Input key={k} label={EXTRACT_LABELS[k]} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
      ))}
      <Input label="Chứng nhận" hint="Cách nhau bằng dấu phẩy" value={certs} onChange={(e) => setCerts(e.target.value)} />
      <div className="flex justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button
          loading={edit.isPending}
          onClick={async () => {
            const clean = (v: string) => (v.trim() ? v.trim() : null);
            await edit.mutateAsync({
              id: doc.id,
              doc_number: clean(num),
              extracted: {
                ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, clean(v)])),
                certifications: certs.split(",").map((c) => c.trim()).filter(Boolean),
              },
            });
            notifySuccess("Đã lưu thông tin chứng từ");
            onClose();
          }}
        >
          Lưu
        </Button>
      </div>
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
            notifySuccess("Đã lưu chứng từ, AI đang đọc");
            onClose();
          }}
        >
          Lưu chứng từ
        </Button>
      </div>
    </div>
  );
}
