"use client";

import { ArrowRight, BookUser, Users } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Badge, Card, DateTime, EmptyState, Money, PageHeader, SkeletonList, Switch, TabLinks } from "@/components/ui";
import { useCotrialOffers, useSetExcluded, useTesterRegistry, type CotrialOffer, type RegistryTester, type TesterHistory } from "@/lib/api/crm";
import { KHACH_SECTIONS, KHACH_TRIAL_TABS } from "@/lib/desk-sections";


/** «Mời thử cùng» (27/11): lời mời theo món đang thử + sổ người dùng thử (đăng ký một lần ở /dung-thu). */
export function CotrialScreen() {
  const registry = useSearchParams().get("tab") === "so";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={KHACH_SECTIONS} active="trial" />
      <TabLinks aria-label="Dùng thử" items={KHACH_TRIAL_TABS} active={registry ? "testers-book" : "offers"} />
      {registry ? <Registry /> : <Offers />}
    </div>
  );
}

function Offers() {
  const { data, isPending, error } = useCotrialOffers();
  if (isPending) return <SkeletonList rows={2} />;
  if (error) return <EmptyState tone="error" title="Chưa tải được lời mời" description={error.message} />;
  if (!data.length) {
    return (
      <EmptyState
        icon={<Users />}
        title="Chưa có lời mời nào"
        action={
          <Link href="/desk/ban-chon?tab=trial" className="text-accent hover:underline">
            Tới Bàn chọn
          </Link>
        }
      />
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {data.map((o) => (
        <li key={o.id}>
          <OfferItem o={o} />
        </li>
      ))}
    </ul>
  );
}

function OfferItem({ o }: { o: CotrialOffer }) {
  const applied = Object.values(o.counts).reduce((a, b) => a + (b ?? 0), 0);
  const waiting = o.counts.refund_proposed ?? 0;
  return (
    <Link href={`/desk/khach/dung-thu/${o.id}`} className="flex items-center gap-3 rounded-md border border-line bg-surface p-3 transition-colors hover:border-line-strong">
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="truncate text-[15px] font-semibold">{o.title}</span>
          <Badge tone={o.status === "open" ? "success" : "neutral"}>{o.status === "open" ? "Đang mở" : "Đã đóng"}</Badge>
          {waiting ? <Badge tone="warning">{waiting} chờ hoàn tiền</Badge> : null}
        </span>
        <span className="block text-[13px] text-ink-2">
          <Money value={o.price_vnd} /> · hoàn <Money value={o.refund_amount_vnd} /> · {applied} đăng ký · chọn {o.taken}/{o.slots} · tạo{" "}
          <DateTime value={o.created_at} format="date" />
        </span>
      </span>
      <ArrowRight className="size-4 shrink-0 text-ink-3" aria-hidden />
    </Link>
  );
}

export function HistoryLine({ h }: { h: TesterHistory }) {
  return (
    <span className="text-[13px] text-ink-2">
      {h.orders} đơn · thử cùng {h.trials} lần · gửi đủ {h.completed}
      {h.missed ? <span className="text-seal"> · lỡ hạn {h.missed}</span> : null}
      {h.dropped ? <span className="text-seal"> · bỏ ngang {h.dropped}</span> : null}
    </span>
  );
}

function Registry() {
  const { data, isPending, error } = useTesterRegistry();
  if (isPending) return <SkeletonList rows={3} />;
  if (error) return <EmptyState tone="error" title="Chưa tải được sổ" description={error.message} />;
  if (!data.length) {
    return (
      <EmptyState
        icon={<BookUser />}
        title="Sổ còn trống"
      />
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {data.map((t) => (
        <li key={t.id}>
          <RegistryRow t={t} />
        </li>
      ))}
    </ul>
  );
}

function RegistryRow({ t }: { t: RegistryTester }) {
  const set = useSetExcluded();
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/desk/khach/so-khach/${t.customer_id}`} className="text-[15px] font-semibold hover:underline">
          {t.name ?? "Chưa có tên"}
        </Link>
        <span className="text-[13px] text-ink-2">{t.phone ?? t.email ?? ""}</span>
      </div>
      <HistoryLine h={t.history} />
      {t.interests.length ? <p className="text-[13px] text-ink-2">Quan tâm: {t.interests.join(", ")}</p> : null}
      <Switch
        label="Loại trừ khỏi lời mời sau"
        description={t.excluded_reason ?? undefined}
        checked={t.excluded}
        disabled={set.isPending}
        onChange={(v) => set.mutate({ id: t.id, excluded: v })}
      />
    </Card>
  );
}
