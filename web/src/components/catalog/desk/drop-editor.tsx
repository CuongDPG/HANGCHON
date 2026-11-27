"use client";

import { ExternalLink, PackageCheck, Plus, Rocket, Square, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, SectionLabel } from "@/components/ui/card";
import { useConfirm } from "@/components/ui/confirm";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { InlineSelect } from "@/components/ui/inline-select";
import { Sheet } from "@/components/ui/overlay";
import { PageHeader } from "@/components/ui/page-header";
import { notifySuccess } from "@/components/ui/toast";
import { useSession } from "@/lib/api/auth";
import {
  DROP_STATUS_LABELS,
  deskDropApi,
  useDeskDrop,
  useDeskProducts,
  useDropMutation,
  type DeskDrop,
  type DropInput,
} from "@/lib/api/catalog";
import { formatVnd } from "@/lib/format";
import { DeskMoreMenu } from "@/components/desk/desk-more-menu";
import { DROP_TONE, fromLocalInput, toLocalInput } from "./drops-screen";

type Row = { product_id: string; price_vnd: string; slots_total: string; max_per_order: string; reserved: number };
type Draft = { title: string; description: string; opens_at: string; closes_at: string; expected_arrival_date: string; deposit_pct: string; items: Row[] };

function toDraft(d: DeskDrop): Draft {
  return {
    title: d.title,
    description: d.description ?? "",
    opens_at: toLocalInput(d.opens_at),
    closes_at: toLocalInput(d.closes_at),
    expected_arrival_date: d.expected_arrival_date ?? "",
    deposit_pct: d.deposit_pct === null ? "" : String(d.deposit_pct),
    items: d.items.map((i) => ({
      product_id: i.product_id,
      price_vnd: String(i.price_vnd),
      slots_total: i.slots_total === null ? "" : String(i.slots_total),
      max_per_order: i.max_per_order === null ? "" : String(i.max_per_order),
      reserved: i.slots_reserved,
    })),
  };
}

function toInput(d: Draft): DropInput {
  const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[^\d]/g, "")));
  return {
    title: d.title.trim(),
    description: d.description.trim() || null,
    opens_at: fromLocalInput(d.opens_at),
    closes_at: fromLocalInput(d.closes_at),
    expected_arrival_date: d.expected_arrival_date || null,
    deposit_pct: n(d.deposit_pct),
    items: d.items.map((i) => ({ product_id: i.product_id, price_vnd: n(i.price_vnd), slots_total: n(i.slots_total), max_per_order: n(i.max_per_order) })),
  };
}

/** Sửa một đợt (e3): món, giá trong đợt, số suất; mở / đóng / đánh dấu hàng về. */
export function DropEditor({ id }: { id: string }) {
  const { data: d, isPending, error } = useDeskDrop(id);
  const products = useDeskProducts({ status: "published" });
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const confirm = useConfirm();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [arrivedOpen, setArrivedOpen] = useState(false);
  const [arrivedOn, setArrivedOn] = useState(() => new Date().toISOString().slice(0, 10));
  // dữ liệu máy chủ đổi (vừa lưu, vừa tải) → làm mới bản nháp ngay trong lúc render (không cần effect)
  const [source, setSource] = useState<DeskDrop | undefined>();
  if (d && d !== source) {
    setSource(d);
    setDraft(toDraft(d));
  }

  const save = useDropMutation(id, (body: DropInput) => deskDropApi.patch(id, body));
  const open = useDropMutation(id, async (body: DropInput | null) => {
    if (body) await deskDropApi.patch(id, body);
    return deskDropApi.open(id);
  });
  const close = useDropMutation(id, () => deskDropApi.close(id));
  const cancel = useDropMutation(id, () => deskDropApi.cancel(id));
  const arrived = useDropMutation(id, (day: string) => deskDropApi.arrived(id, day));

  if (isPending || (d && !draft))
    return (
      <div className="flex flex-col gap-4">
        <PageHeader loading backHref="/desk/san-pham/dot" />
        <SkeletonList rows={5} />
      </div>
    );
  if (error || !d || !draft)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được đợt" backHref="/desk/san-pham/dot" />
        <EmptyState tone="error" title="Chưa tải được đợt" description={error?.message} />
      </div>
    );

  const editable = ["draft", "pending_review", "scheduled", "open"].includes(d.status);
  const dirty = JSON.stringify(toInput(draft)) !== JSON.stringify(toInput(toDraft(d)));
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft({ ...draft, [k]: v });
  const setRow = (i: number, r: Partial<Row>) => set("items", draft.items.map((x, j) => (j === i ? { ...x, ...r } : x)));
  const published = products.data?.items ?? [];
  const nameOf = (pid: string) => d.product_names[pid] ?? published.find((p) => p.id === pid)?.name ?? "Món đã ẩn";
  const addable = published.filter((p) => !draft.items.some((i) => i.product_id === p.id));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={`${d.label} · ${d.title}`}
        backHref="/desk/san-pham/dot"
        badge={<Badge tone={DROP_TONE[d.status]}>{DROP_STATUS_LABELS[d.status]}</Badge>}
        actions={
          <>
            {["draft", "pending_review"].includes(d.status) ? (
              <Button
                size="sm"
                icon={<Rocket className="size-4" />}
                loading={open.isPending}
                onClick={() =>
                  open.mutate(dirty ? toInput(draft) : null, {
                    onSuccess: (x) => notifySuccess(x.status === "open" ? "Đã mở đợt" : x.status === "scheduled" ? "Đã hẹn giờ mở" : "Đã gửi chị duyệt"),
                  })
                }
              >
                {isOwner ? "Mở đợt" : "Gửi duyệt"}
              </Button>
            ) : null}
            {dirty && editable ? (
              <Button size="sm" variant="secondary" loading={save.isPending} onClick={() => save.mutate(toInput(draft), { onSuccess: () => notifySuccess("Đã lưu") })}>
                Lưu
              </Button>
            ) : null}
            {isOwner && ["open", "scheduled"].includes(d.status) ? (
              <Button
                size="sm"
                variant="secondary"
                icon={<Square className="size-4" />}
                onClick={async () => {
                  if (await confirm({ title: "Đóng đợt ngay?", message: "Khách không đặt thêm được. Hệ thống sẽ tổng hợp số lượng để đặt nguồn.", confirmLabel: "Đóng đợt" }))
                    close.mutate(undefined, { onSuccess: () => notifySuccess("Đã đóng đợt") });
                }}
              >
                Đóng đợt
              </Button>
            ) : null}
            {isOwner && ["closed", "sourcing", "arriving"].includes(d.status) ? (
              <Button size="sm" variant="secondary" icon={<PackageCheck className="size-4" />} onClick={() => setArrivedOpen(true)}>
                Hàng đã về
              </Button>
            ) : null}
            <DeskMoreMenu
              items={[
                d.status !== "draft" && d.status !== "pending_review" && d.status !== "cancelled" && {
                  href: `/dot/${d.slug}`,
                  target: "_blank",
                  label: "Xem trên web",
                  icon: <ExternalLink aria-hidden />,
                },
                isOwner &&
                  ["draft", "pending_review", "scheduled"].includes(d.status) && {
                    label: "Huỷ đợt",
                    icon: <XCircle aria-hidden />,
                    danger: true,
                    onSelect: async () => {
                      if (await confirm({ title: "Huỷ đợt này?", message: "Đợt sẽ không hiện trên web nữa.", confirmLabel: "Huỷ đợt", tone: "danger" }))
                        cancel.mutate(undefined);
                    },
                  },
              ]}
            />
          </>
        }
      />
      {d.reminder_count ? (
        <p className="text-[14px] text-ink-2">{d.reminder_count} khách đã bấm «Nhắc mình». Khi đợt mở, AI soạn tin nhắc để chị duyệt.</p>
      ) : null}

      <section className="flex flex-col gap-3">
        <SectionLabel>Thông tin đợt</SectionLabel>
        <Input label="Tên đợt" value={draft.title} onChange={(e) => set("title", e.target.value)} disabled={!editable} maxLength={200} />
        <Textarea label="Giới thiệu" value={draft.description} onChange={(e) => set("description", e.target.value)} disabled={!editable} rows={2} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label="Giờ mở (bỏ trống = mở ngay khi duyệt)" type="datetime-local" value={draft.opens_at} onChange={(e) => set("opens_at", e.target.value)} disabled={!editable} />
          <Input label="Hạn chót đặt" type="datetime-local" value={draft.closes_at} onChange={(e) => set("closes_at", e.target.value)} disabled={!editable} />
          <Input label="Hàng về dự kiến" type="date" value={draft.expected_arrival_date} onChange={(e) => set("expected_arrival_date", e.target.value)} disabled={!editable} />
          <Input label="Đặt cọc (%)" inputMode="numeric" value={draft.deposit_pct} onChange={(e) => set("deposit_pct", e.target.value)} disabled={!editable} />
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <SectionLabel>Món trong đợt</SectionLabel>
        {draft.items.length === 0 ? <p className="text-[14px] text-ink-2">Chưa có món nào. Chỉ món đang trên kệ mới thêm được.</p> : null}
        {draft.items.map((row, i) => (
          <Card key={row.product_id} className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <p className="min-w-0 truncate text-[15px] font-semibold">{nameOf(row.product_id)}</p>
              <IconButton
                label="Bỏ khỏi đợt"
                icon={<Trash2 />}
                disabled={!editable || row.reserved > 0}
                onClick={() => set("items", draft.items.filter((_, j) => j !== i))}
              />
            </div>
            <div className="grid grid-cols-[1.5fr_1fr_1fr] gap-2">
              <Input label="Giá (đ)" inputMode="numeric" value={row.price_vnd} onChange={(e) => setRow(i, { price_vnd: e.target.value })} disabled={!editable} />
              <Input label="Số suất" inputMode="numeric" value={row.slots_total} onChange={(e) => setRow(i, { slots_total: e.target.value })} disabled={!editable} hint={row.reserved ? `Đã đặt ${row.reserved}` : "Trống = không giới hạn"} />
              <Input label="Tối đa/đơn" inputMode="numeric" value={row.max_per_order} onChange={(e) => setRow(i, { max_per_order: e.target.value })} disabled={!editable} />
            </div>
          </Card>
        ))}
        {editable && addable.length ? (
          <InlineSelect
            label="Thêm món"
            placeholder="Chọn món trên kệ"
            value={null}
            onChange={(pid) => {
              const p = addable.find((x) => x.id === pid)!;
              set("items", [...draft.items, { product_id: pid, price_vnd: String(p.price_vnd), slots_total: "", max_per_order: "", reserved: 0 }]);
            }}
            options={addable.map((p) => ({ value: p.id, label: p.name, hint: formatVnd(p.price_vnd) }))}
          />
        ) : null}
        {editable && !addable.length && !draft.items.length ? (
          <Button variant="ghost" size="sm" icon={<Plus className="size-4" />} disabled>
            Chưa có món nào trên kệ để thêm
          </Button>
        ) : null}
      </section>

      <Sheet
        open={arrivedOpen}
        onClose={() => setArrivedOpen(false)}
        title="Hàng đã về"
        footer={
          <Button block loading={arrived.isPending} onClick={() => arrived.mutate(arrivedOn, { onSuccess: () => { setArrivedOpen(false); notifySuccess("Đã ghi hàng về"); } })}>
            Ghi nhận
          </Button>
        }
      >
        <Input label="Ngày hàng về" type="date" value={arrivedOn} onChange={(e) => setArrivedOn(e.target.value)} />
      </Sheet>
    </div>
  );
}
