"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Badge, Button, Card, DateTime, Money, ProgressBar, SectionLabel, notifySuccess, useConfirm } from "@/components/ui";
import { deskDropApi } from "@/lib/api/catalog";
import type { DropOverview } from "@/lib/api/orders";

/** «Chốt đợt sớm»: đóng đợt là việc của catalog → gọi endpoint của catalog; đóng xong orders chốt đơn, supply soạn đơn đặt. */
function CloseEarlyButton({ drop }: { drop: DropOverview }) {
  const confirm = useConfirm();
  const qc = useQueryClient();
  const close = useMutation({
    mutationFn: () => deskDropApi.close(drop.id),
    onSuccess: () => {
      notifySuccess(`Đã chốt ${drop.code}. Đơn đặt nhà cung cấp đang chờ chị duyệt.`);
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["catalog", "drops"] });
      qc.invalidateQueries({ queryKey: ["control"] });
    },
  });
  return (
    <Button
      size="sm"
      variant="secondary"
      aria-label={`Chốt đợt sớm ${drop.code}`}
      loading={close.isPending}
      onClick={async () => {
        const ok = await confirm({
          title: `Chốt ${drop.code} ngay?`,
          message: "Đợt ngừng nhận đơn, AI cộng số lượng và soạn đơn đặt nhà cung cấp để chị duyệt.",
          confirmLabel: "Chốt đợt",
        });
        if (ok) close.mutate();
      }}
    >
      Chốt đợt sớm
    </Button>
  );
}

const DROP_STATUS: Record<string, string> = {
  open: "đang mở",
  scheduled: "sắp mở",
  closed: "đã chốt",
  sourcing: "đang đặt nguồn",
  arriving: "hàng đang về",
  fulfilling: "đang giao",
};

/** Thẻ đợt gom (g3): suất đã đặt, doanh thu, số lượng theo món để đặt nguồn. */
export function DropCard({ drop }: { drop: DropOverview }) {
  const open = drop.status === "open";
  return (
    <Card tone={open ? "accent" : "default"} className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold">
            {drop.code} · {DROP_STATUS[drop.status] ?? drop.status}
          </p>
          <p className="truncate text-[13px] text-ink-2">{drop.title}</p>
        </div>
        {open && drop.closes_at ? (
          <Badge tone="warning">
            chốt <DateTime value={drop.closes_at} format="relative" />
          </Badge>
        ) : drop.expected_arrival_date ? (
          <Badge tone="neutral">về khoảng <DateTime value={drop.expected_arrival_date} format="dayMonth" /></Badge>
        ) : null}
      </div>
      {drop.slots_total ? <ProgressBar value={drop.slots_taken} max={drop.slots_total} label={`${drop.slots_taken} trên ${drop.slots_total} suất`} /> : null}
      <div className="flex items-baseline justify-between text-[14px]">
        <span>
          {drop.slots_taken}
          {drop.slots_total ? `/${drop.slots_total}` : ""} suất · {drop.orders_total} đơn
          {drop.orders_pending ? <span className="text-ink-2"> ({drop.orders_pending} chờ tiền)</span> : null}
        </span>
        <Money value={drop.revenue_vnd} compact className="font-semibold" />
      </div>
      {open ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Link href={`/desk/san-pham/dot/${drop.id}`} className="text-[14px] text-accent">
            Xem đợt
          </Link>
          <CloseEarlyButton drop={drop} />
        </div>
      ) : null}
      <details className="text-[14px]">
        <summary className="cursor-pointer text-accent">Số lượng theo món</summary>
        <ul className="mt-2 flex flex-col gap-1">
          {drop.items.map((i) => (
            <li key={i.drop_item_id} className="flex justify-between gap-3">
              <span className="min-w-0 truncate">{i.name}</span>
              <span className="shrink-0 tabular-nums">
                <b>{i.quantity_confirmed}</b>
                {i.quantity_pending ? <span className="text-ink-2"> +{i.quantity_pending} chờ tiền</span> : null}
                {i.slots_total ? <span className="text-ink-3"> /{i.slots_total}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}

/** «HÀNG ĐANG VỀ»: lô hàng của các đợt (đọc từ supply). */
export function InboundList({ drops }: { drops: DropOverview[] }) {
  const lots = drops.flatMap((d) => d.inbound.filter((l) => l.status !== "delivered").map((l) => ({ ...l, drop: d.code })));
  if (!lots.length) return null;
  return (
    <section className="flex flex-col gap-2">
      <SectionLabel>Hàng đang về</SectionLabel>
      {lots.map((l) => (
        <Card key={l.id} className="flex flex-col gap-0.5 py-3">
          <p className="text-[15px] font-semibold">
            {l.code ?? "Lô hàng"} · {l.drop}
          </p>
          <p className="text-[13px] text-ink-2">
            {l.last_note ?? l.status_label}
            {l.last_at ? (
              <>
                {" "}
                <DateTime value={l.last_at} format="dayMonth" />
              </>
            ) : null}
            {l.eta ? (
              <>
                {" "}
                · về khoảng <DateTime value={l.eta} format="dayMonth" />
              </>
            ) : null}
          </p>
        </Card>
      ))}
    </section>
  );
}
