"use client";

import { Printer } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Button, EmptyState, Money, PageHeader, SkeletonList } from "@/components/ui";
import { CARRIER_LABELS, useLabels } from "@/lib/api/orders";

/** In nhãn A6 (105 × 148 mm) cho các đơn đã có vận đơn (g4). Khi in chỉ in phần nhãn. */
export function LabelsPrint() {
  const ids = useSearchParams().getAll("ids");
  const q = useLabels(ids);
  return (
    <div className="flex flex-col gap-4">
      <style>{`
        @page { size: 105mm 148mm; margin: 0; }
        @media print {
          body * { visibility: hidden !important; }
          #nhan-in, #nhan-in * { visibility: visible !important; }
          #nhan-in { position: absolute; inset: 0; }
          .nhan { break-after: page; border: 0 !important; margin: 0 !important; }
        }
      `}</style>
      <PageHeader
        title="In nhãn"
        backHref="/desk/don-hang?nhom=cho_giao"
        eyebrow="Khổ A6"
        actions={
          <Button size="sm" icon={<Printer className="size-4" />} onClick={() => window.print()} disabled={!q.data?.length}>
            In
          </Button>
        }
      />
      {!ids.length ? (
        <EmptyState title="Chưa chọn đơn nào" description="Chọn đơn ở mục Chờ giao rồi bấm Tạo vận đơn." />
      ) : q.isPending ? (
        <SkeletonList rows={2} />
      ) : q.isError ? (
        <EmptyState tone="error" title="Chưa tải được nhãn" description={q.error.message} />
      ) : !q.data.length ? (
        <EmptyState title="Các đơn này chưa có vận đơn" />
      ) : (
        <div id="nhan-in" className="flex flex-wrap gap-4">
          {q.data.map((l) => (
            <article key={l.order_id} className="nhan flex h-[148mm] w-[105mm] max-w-full flex-col gap-2 border border-ink bg-white p-[6mm] text-[#000]" style={{ fontFamily: "var(--font-sans)" }}>
              <div className="flex items-baseline justify-between border-b border-[#000] pb-1.5">
                <span className="text-[18px] font-extrabold">{CARRIER_LABELS[l.carrier] ?? l.carrier}</span>
                <span className="text-[12px]">{l.service}</span>
              </div>
              <p className="text-center font-mono text-[22px] font-bold tracking-wider">{l.tracking_code}</p>
              <div className="text-[13px]">
                <p className="text-[11px] uppercase">Người nhận</p>
                <p className="text-[16px] font-bold">{l.recipient_name}</p>
                <p className="text-[15px] font-semibold">{l.recipient_phone}</p>
                <p>{l.address}</p>
              </div>
              <div className="text-[12px]">
                <p className="text-[11px] uppercase">Hàng</p>
                <p>{l.items_summary}</p>
                {l.weight_grams ? <p>Khối lượng: {l.weight_grams} g</p> : null}
                {l.note ? <p>Ghi chú: {l.note}</p> : null}
              </div>
              <div className="mt-auto flex items-end justify-between border-t border-[#000] pt-1.5">
                <div>
                  <p className="text-[11px] uppercase">Thu hộ</p>
                  <Money value={l.cod_amount_vnd} className="text-[20px] font-extrabold" />
                </div>
                <div className="text-right">
                  <p className="text-[11px] uppercase">Mã đơn</p>
                  <p className="text-[16px] font-bold">{l.code}</p>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
