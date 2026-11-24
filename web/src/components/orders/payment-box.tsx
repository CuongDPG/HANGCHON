"use client";

import { Copy, QrCode } from "lucide-react";
import { Badge, Card, DateTime, IconButton, Money, notifySuccess } from "@/components/ui";
import type { PaymentInfo } from "@/lib/api/orders";

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    notifySuccess(`Đã chép ${what}`);
  } catch {
    /* trình duyệt chặn: bỏ qua */
  }
}

function Row({ label, value, copyText }: { label: string; value: React.ReactNode; copyText?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line py-2 first:border-t-0">
      <span className="text-[14px] text-ink-2">{label}</span>
      <span className="flex min-w-0 items-center gap-1 text-right font-semibold">
        <span className="min-w-0 break-all">{value}</span>
        {copyText ? <IconButton label={`Chép ${label.toLowerCase()}`} icon={<Copy />} size="sm" onClick={() => copy(copyText, label.toLowerCase())} className="-mr-2" /> : null}
      </span>
    </div>
  );
}

/** Khối chuyển khoản VietQR: mã QR có sẵn số tiền + nội dung (mã đơn); trang tự cập nhật khi tiền về. */
export function PaymentBox({ payment, deposit }: { payment: PaymentInfo; deposit: boolean }) {
  return (
    <Card tone="accent" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-sans text-[16px] font-semibold">{deposit ? "Chuyển khoản đặt cọc" : "Chuyển khoản bằng mã QR"}</h2>
        <Badge tone="warning">Chờ tiền về</Badge>
      </div>
      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-start">
        {payment.qr_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- ảnh SVG do API dựng
          <img src={payment.qr_url} alt="Mã VietQR chuyển khoản" width={200} height={200} className="size-[200px] shrink-0 rounded-md border border-line bg-white p-2" />
        ) : (
          <div className="grid size-[200px] place-items-center rounded-md bg-soft text-ink-3">
            <QrCode className="size-10" aria-hidden />
          </div>
        )}
        <div className="w-full min-w-0 flex-1">
          <Row label="Số tiền" value={<Money value={payment.amount_due_vnd} />} copyText={String(payment.amount_due_vnd)} />
          <Row label="Nội dung" value={payment.transfer_content} copyText={payment.transfer_content ?? undefined} />
          <Row label="Số tài khoản" value={payment.account_no} copyText={payment.account_no ?? undefined} />
          <Row label="Chủ tài khoản" value={payment.account_name} />
          <Row label="Ngân hàng" value={payment.bank_code} />
        </div>
      </div>
      <p className="text-[14px] text-ink-2">
        Quét mã bằng app ngân hàng, giữ nguyên nội dung <b className="text-ink">{payment.transfer_content}</b> để hệ thống tự khớp. Trang này tự cập
        nhật khi đã nhận tiền.
        {payment.due_at ? (
          <>
            {" "}
            Mình giữ suất tới <DateTime value={payment.due_at} format="dateTime" />.
          </>
        ) : null}
      </p>
    </Card>
  );
}
