"use client";

import { useState } from "react";
import { Button, DataList, Input, Money, Sheet, notifyError, notifySuccess } from "@/components/ui";
import { usePrepareInvoice, type InvoiceCandidate, type InvoiceProposeResult } from "@/lib/api/finance";

/**
 * Soạn hoá đơn điện tử cho một đơn đã thanh toán (k5). Hoá đơn đi qua hàng chờ duyệt (`finance.issue_invoice`);
 * nếu đang ở mức «Hỏi chị», trả về việc chờ để chị duyệt ngay ở bước sau.
 */
export function InvoiceSheet({
  order,
  onClose,
  onPending,
}: {
  order: InvoiceCandidate | null;
  onClose: () => void;
  onPending: (approvalItemId: string) => void;
}) {
  return (
    <Sheet open={!!order} onClose={onClose} title="Soạn hoá đơn điện tử" description={order ? `Đơn ${order.code}` : undefined}>
      {order ? <InvoiceForm key={order.order_id} order={order} onClose={onClose} onPending={onPending} /> : null}
    </Sheet>
  );
}

function InvoiceForm({ order, onClose, onPending }: { order: InvoiceCandidate; onClose: () => void; onPending: (id: string) => void }) {
  const [buyer, setBuyer] = useState({ buyer_name: order.recipient_name, buyer_tax_code: "", buyer_email: "", buyer_address: "" });
  const prepare = usePrepareInvoice();

  function done(res: InvoiceProposeResult) {
    if (res.outcome === "applied") notifySuccess(`Đã phát hành hoá đơn số ${res.invoice.number}`);
    else if (res.outcome === "blocked") notifyError("Việc phát hành hoá đơn đang tắt. Bật lại ở Mức tự chủ.");
    else if (res.outcome === "failed") notifyError(res.error ?? "Phát hành lỗi.");
    onClose();
    if (res.outcome === "pending" && res.approval_item_id) onPending(res.approval_item_id);
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        done(await prepare.mutateAsync({ order_id: order.order_id, ...buyer }));
      }}
    >
      <DataList items={[{ label: "Tổng tiền đơn", value: <Money value={order.total_vnd} />, strong: true }]} />
      <Input label="Người mua" value={buyer.buyer_name} onChange={(e) => setBuyer({ ...buyer, buyer_name: e.target.value })} required />
      <Input
        label="Mã số thuế (nếu khách cần)"
        inputMode="numeric"
        value={buyer.buyer_tax_code}
        onChange={(e) => setBuyer({ ...buyer, buyer_tax_code: e.target.value })}
        hint="Khách lẻ thì để trống."
      />
      <Input label="Email nhận hoá đơn" type="email" value={buyer.buyer_email} onChange={(e) => setBuyer({ ...buyer, buyer_email: e.target.value })} />
      <Input
        label="Địa chỉ trên hoá đơn"
        placeholder="Để trống = địa chỉ giao hàng"
        value={buyer.buyer_address}
        onChange={(e) => setBuyer({ ...buyer, buyer_address: e.target.value })}
      />
      <div className="mt-1 flex gap-2 [&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={prepare.isPending} disabled={!buyer.buyer_name.trim()}>
          Soạn hoá đơn
        </Button>
      </div>
      <p className="text-[13px] text-ink-2">Dòng hàng lấy từ đơn. Chị xem lại bản nháp rồi mới phát hành.</p>
    </form>
  );
}
