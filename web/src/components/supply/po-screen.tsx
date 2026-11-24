"use client";

import { Check, Copy, PackageCheck, RotateCw, Send, Wallet, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Button,
  Card,
  DataList,
  DateTime,
  EmptyState,
  Input,
  LevelTag,
  Money,
  PageHeader,
  SectionLabel,
  Segmented,
  Sheet,
  SkeletonList,
  Textarea,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import {
  INBOUND_LABELS,
  PO_KIND_LABELS,
  useApproveItem,
  usePOAction,
  usePurchaseOrder,
  useReturnItem,
  useUpdatePO,
  type PurchaseOrder,
} from "@/lib/api/supply";
import { DocumentsBlock, POStatusBadge, moneyAmount } from "./shared";

/** Một đơn đặt mẫu / đặt lô (d5): duyệt (luôn hỏi chị), gửi, trả tiền, nhận hàng, chứng từ. */
export function POScreen({ id }: { id: string }) {
  const { data: po, isPending, error } = usePurchaseOrder(id);
  if (isPending)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Đang tải…" backHref="/desk/nguon-cung" />
        <SkeletonList rows={3} />
      </div>
    );
  if (error)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được đơn" backHref="/desk/nguon-cung" />
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      </div>
    );
  return <PODetail key={`${po.status}:${po.message_draft ?? ""}:${po.paid_vnd}`} po={po} />;
}

function PODetail({ po }: { po: PurchaseOrder }) {
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const act = usePOAction();
  const approve = useApproveItem();
  const ret = useReturnItem();
  const update = useUpdatePO();
  const confirm = useConfirm();
  const [message, setMessage] = useState(po.message_draft ?? "");
  const [returning, setReturning] = useState(false);
  const [paying, setPaying] = useState(false);
  const [receiving, setReceiving] = useState(false);
  const editable = po.status === "draft" || po.status === "pending_approval";
  const qty = po.lines.reduce((a, l) => a + l.quantity, 0);

  async function run(action: "submit" | "compose" | "status", body?: unknown, msg?: string) {
    await act.mutateAsync({ id: po.id, action, body });
    if (msg) notifySuccess(msg);
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={po.candidate_title ?? po.lines[0]?.description ?? po.code}
        eyebrow={`${PO_KIND_LABELS[po.kind].toUpperCase()} · ${po.code}`}
        backHref="/desk/nguon-cung?tab=don"
      />
      <div className="flex flex-wrap items-center gap-2">
        <POStatusBadge status={po.status} />
        {po.ai_generated ? <LevelTag level="review" size="sm">AI soạn, chị duyệt</LevelTag> : null}
        {po.status === "pending_approval" ? <span className="text-[13px] text-ink-2">Đặt hàng luôn chờ chị duyệt.</span> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <DataList
            items={[
              { label: "Nhà cung cấp", value: po.supplier_id ? <Link className="text-accent hover:underline" href={`/desk/nguon-cung/ncc/${po.supplier_id}`}>{po.supplier_name}</Link> : "Chưa rõ" },
              ...(po.agent_name ? [{ label: "Mua hộ qua", value: po.agent_name }] : []),
              { label: "Số lượng", value: `${qty} cái` },
              { label: "Tiền hàng", value: moneyAmount(po.subtotal_amount, po.currency) },
              ...(Number(po.shipping_amount) ? [{ label: "Cước bên bán", value: moneyAmount(po.shipping_amount, po.currency) }] : []),
              { label: "Tỷ giá", value: po.fx_rate ? `${Number(po.fx_rate).toLocaleString("vi-VN")}đ / ${po.currency}` : "—" },
              { label: "Tổng (VND)", value: <Money value={po.total_vnd} />, strong: true },
              { label: "Đã trả", value: <Money value={po.paid_vnd} /> },
              ...(po.expected_at ? [{ label: "Hẹn giao", value: <DateTime value={po.expected_at} format="date" /> }] : []),
            ]}
          />
        </Card>
        <Card>
          <SectionLabel className="mb-2">Dòng hàng</SectionLabel>
          <ul className="flex flex-col divide-y divide-line">
            {po.lines.map((l) => (
              <li key={l.id} className="py-2 first:pt-0 last:pb-0">
                <p className="text-[15px]">{l.description}</p>
                <p className="text-[13px] text-ink-2">
                  {l.quantity} × {moneyAmount(l.unit_price_amount, po.currency)}
                  {l.unit_cost_vnd ? <> · về tay ≈ <Money value={l.unit_cost_vnd} /></> : null}
                  {l.received_qty ? ` · đã nhận ${l.received_qty}${l.defect_qty ? `, lỗi ${l.defect_qty}` : ""}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <section className="flex flex-col gap-2">
        <SectionLabel>Nội dung gửi {po.agent_name ? "bên mua hộ" : "bên bán"}</SectionLabel>
        {editable ? (
          <Textarea aria-label="Nội dung đơn" value={message} onChange={(e) => setMessage(e.target.value)} rows={6} />
        ) : (
          <pre className="rounded-md border border-line bg-surface p-3 font-sans text-[15px] whitespace-pre-wrap">{po.message_draft ?? "—"}</pre>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            icon={<Copy className="size-4" aria-hidden />}
            onClick={async () => {
              await navigator.clipboard.writeText(editable ? message : (po.message_draft ?? ""));
              notifySuccess("Đã chép nội dung");
            }}
          >
            Chép
          </Button>
          {editable ? (
            <Button size="sm" variant="ghost" icon={<RotateCw className="size-4" aria-hidden />} loading={act.isPending} onClick={() => run("compose", undefined, "AI đã soạn lại")}>
              AI soạn lại
            </Button>
          ) : null}
        </div>
        {po.notes ? <p className="text-[14px] whitespace-pre-line text-ink-2">{po.notes}</p> : null}
      </section>

      {/* hành động theo trạng thái */}
      <div className="flex flex-wrap gap-2 max-md:[&>button]:flex-1">
        {po.status === "pending_approval" && isOwner && po.approval_item_id ? (
          <>
            <Button variant="secondary" icon={<X className="size-4" aria-hidden />} onClick={() => setReturning(true)}>
              Trả lại
            </Button>
            <Button
              icon={<Check className="size-4" aria-hidden />}
              loading={approve.isPending}
              onClick={async () => {
                const r = await approve.mutateAsync({ id: po.approval_item_id!, payload: message !== po.message_draft ? { message_draft: message } : undefined });
                if (r.status === "approved") notifySuccess("Đã duyệt đơn, chị gửi cho bên bán rồi bấm «Đã gửi»");
                else notifyError(r.error ?? "Chưa duyệt được");
              }}
            >
              Duyệt đặt hàng
            </Button>
          </>
        ) : null}
        {po.status === "draft" ? (
          <Button
            icon={<Send className="size-4" aria-hidden />}
            loading={act.isPending || update.isPending}
            onClick={async () => {
              if (message !== po.message_draft) await update.mutateAsync({ id: po.id, message_draft: message });
              await run("submit", undefined, "Đã gửi chị duyệt");
            }}
          >
            Gửi chị duyệt
          </Button>
        ) : null}
        {po.status === "approved" ? (
          <Button icon={<Send className="size-4" aria-hidden />} loading={act.isPending} onClick={() => run("status", { to: "sent" }, "Đã đánh dấu gửi; lô hàng về đã được tạo")}>
            Đã gửi cho bên bán
          </Button>
        ) : null}
        {po.status === "sent" ? (
          <Button variant="secondary" loading={act.isPending} onClick={() => run("status", { to: "confirmed" }, "Bên bán đã nhận đơn")}>
            Bên bán đã xác nhận
          </Button>
        ) : null}
        {isOwner && !["draft", "pending_approval", "cancelled"].includes(po.status) && po.paid_vnd < po.total_vnd ? (
          <Button variant="secondary" icon={<Wallet className="size-4" aria-hidden />} onClick={() => setPaying(true)}>
            Ghi đã trả tiền
          </Button>
        ) : null}
        {!["draft", "pending_approval", "cancelled", "received"].includes(po.status) ? (
          <Button variant="secondary" icon={<PackageCheck className="size-4" aria-hidden />} onClick={() => setReceiving(true)}>
            Đếm hàng nhận
          </Button>
        ) : null}
        {!["received", "partially_received", "cancelled"].includes(po.status) ? (
          <Button
            variant="ghost"
            onClick={async () => {
              if (await confirm({ title: "Huỷ đơn này?", message: "Việc chờ duyệt của đơn cũng bị huỷ.", confirmLabel: "Huỷ đơn", tone: "danger" })) {
                await run("status", { to: "cancelled" }, "Đã huỷ đơn");
              }
            }}
          >
            Huỷ đơn
          </Button>
        ) : null}
      </div>

      {po.inbound.length ? (
        <section className="flex flex-col gap-2">
          <SectionLabel>Lô hàng về</SectionLabel>
          {po.inbound.map((s) => (
            <Link key={s.id} href={`/desk/nguon-cung/lo/${s.id}`} className="rounded-md border border-line bg-surface p-3 hover:border-ink-3">
              <span className="font-semibold">{INBOUND_LABELS[s.status]}</span>
              <span className="text-[14px] text-ink-2">
                {s.tracking_code ? ` · ${s.tracking_code}` : ""}
                {s.eta ? " · dự kiến " : ""}
                {s.eta ? <DateTime value={s.eta} format="dayMonth" /> : null}
              </span>
            </Link>
          ))}
        </section>
      ) : null}

      {po.status !== "draft" && po.status !== "pending_approval" ? (
        <section className="flex flex-col gap-2">
          <SectionLabel>Chứng từ nguồn gốc</SectionLabel>
          <DocumentsBlock purchaseOrderId={po.id} missing={po.missing_documents} />
        </section>
      ) : null}

      <ReturnSheet open={returning} onClose={() => setReturning(false)} onSubmit={async (note) => {
        await ret.mutateAsync({ id: po.approval_item_id!, note });
        notifySuccess("Đã trả lại, đơn về nháp");
      }} />
      <PaySheet po={po} open={paying} onClose={() => setPaying(false)} />
      <ReceiveSheet po={po} open={receiving} onClose={() => setReceiving(false)} />
    </div>
  );
}

function ReturnSheet({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Trả lại đơn"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            disabled={!note.trim()}
            onClick={async () => {
              await onSubmit(note.trim());
              setNote("");
              onClose();
            }}
          >
            Trả lại
          </Button>
        </>
      }
    >
      <Textarea label="Lời nhắn" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ví dụ: đổi sang màu xanh, đặt 2 cái" />
    </Sheet>
  );
}

function PaySheet({ po, open, onClose }: { po: PurchaseOrder; open: boolean; onClose: () => void }) {
  const act = usePOAction();
  const [kind, setKind] = useState<"payment" | "deposit">("payment");
  const [amount, setAmount] = useState(String(Math.max(0, po.total_vnd - po.paid_vnd)));
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Ghi khoản đã trả"
      description="Khoản này được ghi vào sổ chi phí (k1)."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            loading={act.isPending}
            disabled={!Number(amount)}
            onClick={async () => {
              await act.mutateAsync({ id: po.id, action: "payments", body: { amount_vnd: Math.round(Number(amount)), kind } });
              notifySuccess("Đã ghi khoản trả");
              onClose();
            }}
          >
            Ghi
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Segmented aria-label="Loại khoản" value={kind} onChange={setKind} block options={[{ value: "payment", label: "Thanh toán" }, { value: "deposit", label: "Đặt cọc" }]} />
        <Input label="Số tiền" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/\D/g, ""))} trailing="đ" />
      </div>
    </Sheet>
  );
}

function ReceiveSheet({ po, open, onClose }: { po: PurchaseOrder; open: boolean; onClose: () => void }) {
  const act = usePOAction();
  const [rows, setRows] = useState(() => po.lines.map((l) => ({ line_id: l.id, received_qty: l.received_qty || l.quantity, defect_qty: l.defect_qty })));
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Đếm hàng nhận"
      description="Số lỗi dùng để chấm điểm uy tín nhà cung cấp."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            loading={act.isPending}
            onClick={async () => {
              await act.mutateAsync({ id: po.id, action: "receive", body: { lines: rows } });
              notifySuccess("Đã ghi nhận hàng");
              onClose();
            }}
          >
            Lưu
          </Button>
        </>
      }
    >
      <ul className="flex flex-col gap-4">
        {po.lines.map((l, i) => (
          <li key={l.id} className="flex flex-col gap-2">
            <p className="text-[15px] font-medium">
              {l.description} <span className="text-ink-2">· đặt {l.quantity}</span>
            </p>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Đã nhận"
                type="number"
                min={0}
                value={rows[i].received_qty}
                onChange={(e) => setRows((r) => r.map((x, j) => (j === i ? { ...x, received_qty: Number(e.target.value) } : x)))}
              />
              <Input
                label="Lỗi"
                type="number"
                min={0}
                value={rows[i].defect_qty}
                onChange={(e) => setRows((r) => r.map((x, j) => (j === i ? { ...x, defect_qty: Number(e.target.value) } : x)))}
              />
            </div>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
