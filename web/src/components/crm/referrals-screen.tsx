"use client";

import { Gift, Plus, Ticket, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  DateTime,
  EmptyState,
  Input,
  LevelTag,
  Money,
  PageHeader,
  SectionLabel,
  Sheet,
  SkeletonList,
  StatTile,
  notifySuccess,
} from "@/components/ui";
import {
  useCreateReferral,
  useManualReferral,
  useReferralStats,
  useReferralUses,
  useReferrals,
  useRewardReferral,
  useVoidReferral,
  type Referral,
  type ReferralUse,
} from "@/lib/api/crm";
import { formatPercent } from "@/lib/format";
import { CustomerPicker } from "./customer-picker";
import { KhachNav } from "./khach-nav";

const USE_STATUS: Record<ReferralUse["status"], { label: string; tone: "warning" | "success" | "neutral" | "accent" }> = {
  pending: { label: "Chờ đơn giao xong", tone: "neutral" },
  qualified: { label: "Đủ điều kiện tặng quà", tone: "warning" },
  rewarded: { label: "Đã tặng quà", tone: "success" },
  void: { label: "Đã huỷ", tone: "neutral" },
};

/** Giới thiệu bạn (h7): mỗi khách một mã. Quà tự áp: bạn mới giảm ngay ở đơn đầu; đơn đó trả tiền và giao xong thì
 *  AI tặng người giới thiệu phần giảm cho đơn kế tiếp (ghi Nhật ký AI, hoàn tác được). Chị vẫn ghi quà tay được. */
export function ReferralsScreen() {
  const stats = useReferralStats();
  const s = stats.data;
  const [pickOpen, setPickOpen] = useState(false);
  const create = useCreateReferral();
  const router = useRouter();

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Giới thiệu bạn"
        actions={<Button size="sm" variant="secondary" icon={<Plus className="size-4" />} onClick={() => setPickOpen(true)}>Tạo mã</Button>}
      />
      <KhachNav active="referral" />
      <Card tone="soft" className="flex items-start gap-2 text-[14px]">
        <LevelTag level="auto" size="sm">AI tự làm</LevelTag>
        <span className="[text-wrap:pretty]">
          Quà cho cả hai tự áp: bạn mới giảm ngay ở đơn đầu; đơn đó trả tiền và giao xong thì người giới thiệu được giảm ở đơn kế tiếp.
          Mỗi khách mới một lần, không áp khi tự giới thiệu mình. Mức quà đổi ở Cài đặt (nhóm Khách).
        </span>
      </Card>
      {stats.error ? (
        <EmptyState tone="error" title="Chưa tải được số liệu" description={stats.error.message} />
      ) : (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <StatTile value={s ? String(s.orders_from_referrals) : "…"} label="đơn từ người được giới thiệu" />
          <StatTile value={s ? <Money value={s.revenue_from_referrals_vnd} compact /> : "…"} label="doanh thu từ giới thiệu" />
          <StatTile
            value={s?.referred_repeat_rate != null ? formatPercent(s.referred_repeat_rate) : "—"}
            label="người được giới thiệu mua lại"
            hint={s?.overall_repeat_rate != null ? `Khách nói chung: ${formatPercent(s.overall_repeat_rate)}` : undefined}
          />
          <StatTile value={s ? `${s.rewarded}/${s.uses}` : "…"} label="lượt đã tặng quà" hint={s ? `${s.codes} mã đã phát` : undefined} />
        </div>
      )}
      <Uses />
      <Codes />
      <CustomerPicker
        open={pickOpen}
        onClose={() => setPickOpen(false)}
        title="Tạo mã giới thiệu cho khách"
        loading={create.isPending}
        onPick={async ([c]) => {
          await create.mutateAsync(c.id);
          setPickOpen(false);
          notifySuccess(`Đã tạo mã cho ${c.name ?? "khách"}`);
          router.refresh();
        }}
      />
    </div>
  );
}

function Uses() {
  const { data, isPending, error } = useReferralUses();
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Lượt giới thiệu</SectionLabel>
      {isPending ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : data.length === 0 ? (
        <EmptyState icon={<Ticket />} title="Chưa có ai dùng mã" description="Khi đơn đầu của người được giới thiệu có mã, lượt đó hiện ở đây." />
      ) : (
        <ul className="flex flex-col gap-2.5">
          {data.map((u) => (
            <li key={u.id}>
              <UseCard u={u} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function UseCard({ u }: { u: ReferralUse }) {
  const reward = useRewardReferral();
  const voidUse = useVoidReferral();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("Phiếu giảm 30.000đ cho đơn sau");
  const st = USE_STATUS[u.status];
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-[15px] [text-wrap:pretty]">
          <span className="font-semibold">{u.referrer_name}</span> giới thiệu <span className="font-semibold">{u.referred_name}</span>
        </p>
        <Badge tone={st.tone} className="shrink-0">
          {st.label}
        </Badge>
      </div>
      <p className="text-[13px] text-ink-2">
        Mã {u.code}
        {u.order_code ? ` · đơn ${u.order_code}` : " · ghi nhận tay"} · <DateTime value={u.created_at} format="date" />
      </p>
      {u.referred_discount_vnd || u.referrer_credit_vnd ? (
        <p className="text-[13px]">
          {u.referred_discount_vnd ? (
            <>
              {u.referred_name} được giảm <Money value={u.referred_discount_vnd} /> ở đơn đầu
            </>
          ) : null}
          {u.referred_discount_vnd && u.referrer_credit_vnd ? " · " : null}
          {u.referrer_credit_vnd ? (
            <>
              {u.referrer_name} được giảm <Money value={u.referrer_credit_vnd} />{" "}
              {u.credit_order_code ? `(đã dùng ở đơn ${u.credit_order_code})` : "cho đơn kế tiếp, chưa dùng"}
            </>
          ) : null}
        </p>
      ) : null}
      {u.status === "pending" || u.status === "qualified" ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant={u.status === "qualified" ? "primary" : "secondary"} icon={<Gift className="size-4" />} onClick={() => setOpen(true)}>
            Đã tặng quà
          </Button>
          <Button size="sm" variant="ghost" loading={voidUse.isPending} onClick={() => voidUse.mutate(u.id)}>
            Huỷ lượt này
          </Button>
        </div>
      ) : null}
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Xác nhận quà cho cả hai"
        description={`Ghi vào sổ khách của ${u.referrer_name} và ${u.referred_name}.`}
        footer={
          <Button
            block
            loading={reward.isPending}
            onClick={async () => {
              await reward.mutateAsync({ useId: u.id, note });
              setOpen(false);
              notifySuccess("Đã ghi nhận quà");
            }}
          >
            Xác nhận
          </Button>
        }
      >
        <Input label="Quà đã tặng" value={note} onChange={(e) => setNote(e.target.value)} />
      </Sheet>
    </Card>
  );
}

function Codes() {
  const { data, isPending, error } = useReferrals();
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Mã giới thiệu</SectionLabel>
      {isPending ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được mã" description={error.message} />
      ) : data.length === 0 ? (
        <EmptyState icon={<Ticket />} title="Chưa phát mã nào" description="Bấm «Tạo mã» để phát mã cho khách quen." />
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {data.map((r) => (
            <li key={r.id}>
              <CodeRow r={r} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CodeRow({ r }: { r: Referral }) {
  const manual = useManualReferral();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5">
      <span className="min-w-0">
        <span className="block font-mono text-[15px] font-semibold tracking-wide">{r.code}</span>
        <span className="block truncate text-[13px] text-ink-2">
          {r.referrer_name} · {r.uses_count} lượt · {r.rewarded_count} đã tặng quà
        </span>
      </span>
      <Button size="sm" variant="ghost" icon={<UserPlus className="size-4" />} onClick={() => setOpen(true)}>
        Ghi nhận tay
      </Button>
      <CustomerPicker
        open={open}
        onClose={() => setOpen(false)}
        title={`Ai được ${r.referrer_name ?? "khách"} giới thiệu?`}
        description="Dùng khi khách báo qua tin nhắn mà đơn không có mã."
        loading={manual.isPending}
        onPick={async ([c]) => {
          await manual.mutateAsync({ referralId: r.id, customerId: c.id });
          setOpen(false);
          notifySuccess("Đã ghi nhận giới thiệu");
        }}
      />
    </div>
  );
}
