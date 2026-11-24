"use client";

import { MapPinned, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Button,
  Card,
  DataList,
  DateTime,
  EmptyState,
  InlineSelect,
  Input,
  LevelTag,
  PageHeader,
  SectionLabel,
  Sheet,
  SkeletonList,
  Timeline,
  notifySuccess,
  type TimelineItem,
} from "@/components/ui";
import { formatDateTime, formatDayMonth } from "@/lib/format";
import {
  INBOUND_FLOW,
  INBOUND_LABELS,
  useInbound,
  useInboundAction,
  useUpdateInbound,
  type Inbound,
  type InboundStatus,
} from "@/lib/api/supply";
import { DocumentsBlock } from "./shared";

/** Một lô hàng về (d7): các mốc đã đặt → kho bên bán → thông quan → về nhà, cập nhật tay hoặc từ hãng vận chuyển. */
export function InboundScreen({ id }: { id: string }) {
  const { data, isPending, error } = useInbound(id);
  if (isPending)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Đang tải…" backHref="/desk/nguon-cung?tab=lo-hang" />
        <SkeletonList rows={3} />
      </div>
    );
  if (error)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được lô hàng" backHref="/desk/nguon-cung?tab=lo-hang" />
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      </div>
    );
  return <InboundDetail key={data.tracking_code ?? ""} s={data} />;
}

function timeline(s: Inbound): TimelineItem[] {
  const reached = new Map(s.milestones.map((m) => [m.status, m]));
  const cur = s.status === "problem" ? -1 : INBOUND_FLOW.indexOf(s.status);
  const items: TimelineItem[] = INBOUND_FLOW.map((st, i) => {
    const m = reached.get(st);
    return {
      title: INBOUND_LABELS[st],
      meta: m ? `${formatDateTime(m.at)}${m.source === "shipping" ? " · từ hãng vận chuyển" : ""}` : i === INBOUND_FLOW.length - 1 && s.eta ? `Dự kiến ${formatDayMonth(s.eta)}` : undefined,
      description: m?.note ?? undefined,
      status: i < cur || (i === cur && st === "delivered") ? "done" : i === cur ? "current" : m ? "done" : "todo",
    };
  });
  if (s.status === "problem") items.push({ title: "Có vấn đề", description: s.problem_note ?? undefined, status: "current" });
  return items;
}

function InboundDetail({ s }: { s: Inbound }) {
  const act = useInboundAction();
  const update = useUpdateInbound();
  const [open, setOpen] = useState(false);
  const [tracking, setTracking] = useState(s.tracking_code ?? "");
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={INBOUND_LABELS[s.status]}
        eyebrow={`LÔ HÀNG${s.code ? ` · ${s.code}` : ""}`}
        backHref="/desk/nguon-cung?tab=lo-hang"
      />
      <div className="grid gap-4 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card>
          <div className="mb-3 flex items-center justify-between gap-2">
            <SectionLabel>Hành trình</SectionLabel>
            <LevelTag level="auto" size="sm" />
          </div>
          <Timeline items={timeline(s)} />
          <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
            <Button size="sm" icon={<MapPinned className="size-4" aria-hidden />} onClick={() => setOpen(true)} disabled={s.status === "delivered"}>
              Cập nhật mốc
            </Button>
            {s.tracking_code ? (
              <Button
                size="sm"
                variant="secondary"
                loading={act.isPending}
                icon={<RefreshCw className="size-4" aria-hidden />}
                onClick={async () => {
                  await act.mutateAsync({ id: s.id, action: "sync" });
                  notifySuccess("Đã hỏi hãng vận chuyển");
                }}
              >
                Hỏi hãng vận chuyển
              </Button>
            ) : null}
          </div>
        </Card>
        <div className="flex flex-col gap-4">
          <Card>
            <DataList
              items={[
                { label: "Đơn", value: s.purchase_order_id ? <Link className="text-accent hover:underline" href={`/desk/nguon-cung/don/${s.purchase_order_id}`}>{s.po_code}</Link> : "—" },
                { label: "Nhà cung cấp", value: s.supplier_name ?? "—" },
                { label: "Dự kiến về", value: s.eta ? <DateTime value={s.eta} format="date" /> : "—" },
                ...(s.received_at ? [{ label: "Đã về", value: <DateTime value={s.received_at} format="dateTime" /> }] : []),
                ...(s.weight_kg ? [{ label: "Cân nặng", value: `${Number(s.weight_kg).toLocaleString("vi-VN")} kg` }] : []),
              ]}
            />
          </Card>
          <form
            className="flex items-end gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              await update.mutateAsync({ id: s.id, tracking_code: tracking.trim() || null });
              notifySuccess("Đã lưu mã vận đơn");
            }}
          >
            <Input label="Mã vận đơn" value={tracking} onChange={(e) => setTracking(e.target.value)} wrapperClassName="flex-1" placeholder="Để AI tự theo dõi" />
            <Button type="submit" variant="secondary" loading={update.isPending}>
              Lưu
            </Button>
          </form>
        </div>
      </div>
      <section className="flex flex-col gap-2">
        <SectionLabel>Chứng từ của lô</SectionLabel>
        <DocumentsBlock inboundId={s.id} missing={s.missing_documents} />
      </section>
      <MilestoneSheet key={s.status} s={s} open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function MilestoneSheet({ s, open, onClose }: { s: Inbound; open: boolean; onClose: () => void }) {
  const act = useInboundAction();
  const next = INBOUND_FLOW[Math.min(INBOUND_FLOW.indexOf(s.status) + 1, INBOUND_FLOW.length - 1)] ?? "delivered";
  const [status, setStatus] = useState<InboundStatus>(next);
  const [note, setNote] = useState("");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Cập nhật mốc"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            loading={act.isPending}
            onClick={async () => {
              await act.mutateAsync({ id: s.id, action: "milestones", body: { status, note: note || null } });
              notifySuccess(status === "delivered" ? "Hàng đã về nhà! Đơn của khách chuyển sang chờ giao." : "Đã cập nhật mốc");
              onClose();
            }}
          >
            Lưu mốc
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <InlineSelect
          label="Mốc"
          value={status}
          onChange={setStatus}
          options={[...INBOUND_FLOW, "problem" as const].map((st) => ({ value: st, label: INBOUND_LABELS[st] }))}
        />
        <Input label="Ghi chú" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ví dụ: kiện 2/3 đã về kho Quảng Châu" />
      </div>
    </Sheet>
  );
}
