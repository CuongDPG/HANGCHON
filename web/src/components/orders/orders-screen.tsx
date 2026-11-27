"use client";

import { Bot, Plus, Printer, Search, Truck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  Checkbox,
  DateTime,
  EmptyState,
  Money,
  notifyError,
  notifySuccess,
  PageHeader,
  SkeletonList,
  Tabs,
  Toolbar,
  ToolbarSearch,
} from "@/components/ui";
import {
  CHANNEL_LABELS,
  GROUPS,
  PAYMENT_LABELS,
  statusTone,
  useCreateShipments,
  useDropOverviews,
  useOrderCounts,
  useOrders,
  type OrderListItem,
  type StatusGroup,
} from "@/lib/api/orders";
import { ORDER_SETTINGS, orderSections } from "@/lib/desk-sections";
import { DropCard, InboundList } from "./drop-card";

/** Đơn hàng và đợt gom (g1, g3, g4): đợt đang mở, đơn theo trạng thái, tìm, tạo đơn, tạo vận đơn hàng loạt. */
export function OrdersScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const group = (params.get("nhom") as StatusGroup | null) ?? "cho_thanh_toan";
  const [q, setQ] = useState(params.get("q") ?? "");
  const [selected, setSelected] = useState<string[]>([]);
  const counts = useOrderCounts();
  const drops = useDropOverviews();
  const orders = useOrders({ nhom: q.trim() ? "tat_ca" : group, q: q.trim() || undefined });
  const ship = useCreateShipments();

  function setGroup(g: StatusGroup) {
    setSelected([]);
    const sp = new URLSearchParams(params.toString());
    sp.set("nhom", g);
    router.replace(`${pathname}?${sp.toString()}`, { scroll: false });
  }

  async function shipSelected() {
    const res = await ship.mutateAsync({ order_ids: selected });
    const ok = res.results.filter((r) => r.status === "applied").length;
    const pending = res.results.filter((r) => r.status === "pending").length;
    const bad = res.results.filter((r) => r.status === "failed" || r.status === "skipped");
    if (ok) notifySuccess(`Đã tạo ${ok} vận đơn`);
    if (pending) notifySuccess(`${pending} vận đơn đang chờ chị duyệt`);
    if (bad.length) notifyError(bad.map((b) => `${b.code}: ${b.message}`).join(" · "));
    if (ok) router.push(`/desk/don-hang/in-nhan?${res.results.filter((r) => r.status === "applied").map((r) => `ids=${r.order_id}`).join("&")}`);
    setSelected([]);
  }

  const c = counts.data;
  const openDrops = (drops.data ?? []).filter((d) => d.status === "open");
  const canShip = group === "cho_giao" && !q.trim();
  // «In nhãn»: đơn đang chọn, hoặc mọi đơn đang giao (đã có vận đơn) khi ở nhóm Đang giao
  const labelIds = selected.length ? selected : group === "dang_giao" && !q.trim() ? (orders.data?.items ?? []).map((o) => o.id) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        sections={orderSections(c)}
        active="orders"
        settings={ORDER_SETTINGS}
        actions={
          <>
            <ButtonLink href="/desk/don-hang/tao" size="sm" icon={<Plus className="size-4" />}>
              Tạo đơn
            </ButtonLink>
            <ButtonLink
              href={labelIds.length ? `/desk/don-hang/in-nhan?${labelIds.map((id) => `ids=${id}`).join("&")}` : "/desk/don-hang/in-nhan"}
              variant="secondary"
              size="sm"
              icon={<Printer className="size-4" />}
            >
              In nhãn
            </ButtonLink>
          </>
        }
      />

      {c && (c.payments_to_review || c.returns_open || c.nhap) ? (
        <div className="flex flex-wrap gap-2">
          {c.payments_to_review ? (
            <Link href="/desk/don-hang/van-hanh?tab=tien" className="rounded-md bg-review-wash px-3 py-1.5 text-[14px] text-review">
              {c.payments_to_review} khoản tiền cần chị xem
            </Link>
          ) : null}
          {c.returns_open ? (
            <Link href="/desk/don-hang/van-hanh?tab=doi-tra" className="rounded-md bg-seal-wash px-3 py-1.5 text-[14px] text-seal">
              {c.returns_open} yêu cầu đổi trả
            </Link>
          ) : null}
          {c.nhap ? (
            <button type="button" onClick={() => setGroup("nhap")} className="inline-flex items-center gap-1.5 rounded-md bg-accent-wash px-3 py-1.5 text-[14px] text-accent">
              <Bot className="size-4" aria-hidden /> {c.nhap} đơn nháp từ tin nhắn
            </button>
          ) : null}
        </div>
      ) : null}

      {drops.isPending ? <SkeletonList rows={1} /> : openDrops.length ? <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{openDrops.map((d) => <DropCard key={d.id} drop={d} />)}</div> : null}

      <Tabs
        aria-label="Nhóm đơn"
        value={q.trim() ? "tat_ca" : group}
        onChange={(g) => {
          setQ("");
          setGroup(g);
        }}
        items={GROUPS.map((g) => ({ value: g.value, label: g.label, count: c ? c[g.value] : undefined }))}
      />
      <Toolbar end={<ToolbarSearch aria-label="Tìm đơn" placeholder="Tìm mã đơn, tên, số điện thoại" value={q} onChange={(e) => setQ(e.target.value)} />} />

      {canShip && orders.data?.items.length ? (
        <div className="flex flex-wrap items-center gap-2">
          <Checkbox
            label="Chọn tất cả"
            checked={selected.length > 0 && selected.length === orders.data.items.length}
            onChange={(e) => setSelected(e.target.checked ? orders.data!.items.map((o) => o.id) : [])}
          />
          <div className="ml-auto flex gap-2">
            <Button size="sm" icon={<Truck className="size-4" />} disabled={!selected.length} loading={ship.isPending} onClick={shipSelected}>
              Tạo vận đơn{selected.length ? ` (${selected.length})` : ""}
            </Button>
          </div>
        </div>
      ) : null}

      {orders.isPending ? (
        <SkeletonList rows={4} />
      ) : orders.isError ? (
        <EmptyState tone="error" title="Chưa tải được đơn" description={orders.error.message} action={<Button onClick={() => orders.refetch()}>Thử lại</Button>} />
      ) : orders.data.items.length === 0 ? (
        <EmptyState icon={<Search />} title={q.trim() ? "Không thấy đơn khớp" : "Chưa có đơn ở mục này"} description={q.trim() ? "Thử mã đơn, tên khác hoặc vài số cuối điện thoại." : undefined} />
      ) : (
        <ul className="flex flex-col gap-2">
          {orders.data.items.map((o) => (
            <OrderRow
              key={o.id}
              order={o}
              selectable={canShip}
              selected={selected.includes(o.id)}
              onSelect={(on) => setSelected((s) => (on ? [...s, o.id] : s.filter((x) => x !== o.id)))}
            />
          ))}
        </ul>
      )}
      {orders.data && orders.data.total > orders.data.items.length ? <p className="text-center text-[13px] text-ink-2">Đang hiện {orders.data.items.length}/{orders.data.total} đơn, tìm để thu hẹp.</p> : null}

      {drops.data ? <InboundList drops={drops.data} /> : null}
    </div>
  );
}

function OrderRow({ order: o, selectable, selected, onSelect }: { order: OrderListItem; selectable: boolean; selected: boolean; onSelect: (on: boolean) => void }) {
  return (
    <li className="flex items-stretch gap-2">
      {selectable ? (
        <div className="flex items-center pl-1">
          <Checkbox label={<span className="sr-only">Chọn đơn {o.code}</span>} checked={selected} onChange={(e) => onSelect(e.target.checked)} />
        </div>
      ) : null}
      <Card flush className="min-w-0 flex-1 transition-colors hover:border-ink-3">
        <Link href={`/desk/don-hang/${o.id}`} className="flex flex-col gap-1 p-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-[15px] font-semibold">
              <span className="tabular-nums">{o.code}</span> · {o.recipient_name}
            </span>
            <Money value={o.total_vnd} className="shrink-0 font-semibold" />
          </div>
          <p className="truncate text-[13px] text-ink-2">{o.items_summary || "Chưa có món"}</p>
          <div className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-ink-2">
            <Badge tone={statusTone(o.status)}>{o.status_label}</Badge>
            <span>{CHANNEL_LABELS[o.channel] ?? o.channel}</span>
            <span aria-hidden>·</span>
            <span>{PAYMENT_LABELS[o.payment_method]}</span>
            {o.drop_code ? (
              <>
                <span aria-hidden>·</span>
                <span>{o.drop_code}</span>
              </>
            ) : null}
            <span aria-hidden>·</span>
            <DateTime value={o.placed_at} format="relative" />
            {o.ai_generated ? <Badge tone="outline">AI soạn</Badge> : null}
            {o.missing_info.length ? <span className="text-seal">Thiếu: {o.missing_info.join(", ")}</span> : null}
            {o.tracking_code ? <span>· {o.tracking_code}</span> : null}
          </div>
        </Link>
      </Card>
    </li>
  );
}
