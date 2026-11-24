"use client";

import { Check, Copy, Languages, MessageSquarePlus, PenLine, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Chip,
  DataList,
  DateTime,
  EmptyState,
  IconButton,
  Input,
  LevelTag,
  PageHeader,
  SectionLabel,
  Sheet,
  SkeletonList,
  Textarea,
  notifySuccess,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { useSession } from "@/lib/api/auth";
import {
  LANGUAGE_LABELS,
  SUPPLIER_KIND_LABELS,
  TOPIC_LABELS,
  num,
  useApproveItem,
  useDraftInquiry,
  useMarkSent,
  usePurchaseOrders,
  useRecordReply,
  useSupplier,
  useSupplierMessages,
  type InquiryTopic,
  type Supplier,
  type SupplierMessage,
} from "@/lib/api/supply";
import { SupplierForm } from "./supply-screen";
import { POStatusBadge } from "./shared";

/** Hồ sơ nhà cung cấp (d1) + nhắn hỏi (d6). */
export function SupplierScreen({ id }: { id: string }) {
  const { data, isPending, error } = useSupplier(id);
  if (isPending)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Đang tải…" backHref="/desk/nguon-cung?tab=ncc" />
        <SkeletonList rows={3} />
      </div>
    );
  if (error)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được" backHref="/desk/nguon-cung?tab=ncc" />
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      </div>
    );
  return <SupplierDetail s={data} />;
}

function pct(v: string | number | null) {
  return v === null ? "—" : `${(num(v) * 100).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`;
}

function SupplierDetail({ s }: { s: Supplier }) {
  const [editing, setEditing] = useState(false);
  const pos = usePurchaseOrders({ supplier_id: s.id });
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={s.name}
        eyebrow={`${SUPPLIER_KIND_LABELS[s.kind].toUpperCase()}${s.country ? ` · ${s.country}` : ""}`}
        backHref="/desk/nguon-cung?tab=ncc"
        actions={<IconButton label="Sửa hồ sơ" icon={<PenLine />} onClick={() => setEditing(true)} />}
      />
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex items-center gap-4">
            <div className={cn("grid size-16 shrink-0 place-items-center rounded-md font-display text-2xl font-extrabold tabular-nums",
              s.is_blocked ? "bg-seal-wash text-seal" : s.trust_score !== null && s.trust_score >= 80 ? "bg-auto-wash text-auto" : "bg-soft")}>
              {s.trust_score ?? "–"}
            </div>
            <div className="min-w-0">
              <p className="text-[15px] font-semibold">{s.trust_label}</p>
              <p className="text-[13px] text-ink-2">{s.trust_basis}</p>
              <p className="mt-0.5 text-[12px] text-ink-3">Điểm tự tính từ lịch sử đúng hẹn và tỉ lệ lỗi.</p>
            </div>
          </Card>
          <Card>
            <DataList
              items={[
                { label: "Tên gốc", value: s.name_original ?? "—" },
                { label: "Nhắn bằng", value: LANGUAGE_LABELS[s.language] ?? s.language },
                { label: "Số đơn", value: s.order_count },
                { label: "Đúng hẹn", value: pct(s.on_time_rate) },
                { label: "Tỉ lệ lỗi", value: pct(s.defect_rate) },
                { label: "Giao trung bình", value: s.avg_lead_days ? `${num(s.avg_lead_days).toLocaleString("vi-VN")} ngày` : "—" },
              ]}
            />
            {s.shop_url ? (
              <a href={s.shop_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[14px] text-accent hover:underline">
                Mở trang shop
              </a>
            ) : null}
            {s.notes ? <p className="mt-2 text-[14px] text-ink-2">{s.notes}</p> : null}
          </Card>
          {pos.data?.items.length ? (
            <section className="flex flex-col gap-2">
              <SectionLabel>Đơn đã đặt</SectionLabel>
              <ul className="flex flex-col gap-2">
                {pos.data.items.map((po) => (
                  <li key={po.id}>
                    <Link href={`/desk/nguon-cung/don/${po.id}`} className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface p-3 hover:border-ink-3">
                      <span className="min-w-0 truncate text-[14px]">
                        {po.code} · {po.candidate_title ?? po.lines[0]?.description}
                      </span>
                      <POStatusBadge status={po.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
        <Messages supplier={s} />
      </div>
      <Sheet open={editing} onClose={() => setEditing(false)} title="Sửa hồ sơ nhà cung cấp">
        {editing ? <SupplierForm initial={s} onClose={() => setEditing(false)} /> : null}
      </Sheet>
    </div>
  );
}

function Messages({ supplier }: { supplier: Supplier }) {
  const { data, isPending } = useSupplierMessages(supplier.id);
  const [asking, setAsking] = useState(false);
  const [replying, setReplying] = useState(false);
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Nhắn hỏi</SectionLabel>
        <LevelTag level="review" size="sm" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" icon={<MessageSquarePlus className="size-4" aria-hidden />} onClick={() => setAsking(true)}>
          AI soạn tin hỏi
        </Button>
        <Button size="sm" variant="secondary" icon={<Languages className="size-4" aria-hidden />} onClick={() => setReplying(true)}>
          Dán câu trả lời
        </Button>
      </div>
      {isPending ? (
        <SkeletonList rows={2} />
      ) : !data?.length ? (
        <p className="text-[14px] text-ink-2">Chưa nhắn gì. AI soạn tin {LANGUAGE_LABELS[supplier.language]?.toLowerCase() ?? ""} kèm bản dịch để chị duyệt rồi gửi.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((m) => (
            <MessageBubble key={m.id} m={m} />
          ))}
        </ul>
      )}
      <InquirySheet supplierId={supplier.id} open={asking} onClose={() => setAsking(false)} />
      <ReplySheet supplierId={supplier.id} open={replying} onClose={() => setReplying(false)} />
    </section>
  );
}

const MSG_STATUS: Record<SupplierMessage["status"], string> = {
  draft: "Nháp (chị trả lại)",
  pending_review: "Chờ chị duyệt",
  approved: "Đã duyệt, chờ gửi",
  sent: "Đã gửi",
  received: "Bên bán trả lời",
  failed: "Gửi lỗi",
};

function MessageBubble({ m }: { m: SupplierMessage }) {
  const { user } = useSession();
  const approve = useApproveItem();
  const sent = useMarkSent();
  const out = m.direction === "outbound";
  const ex = m.extracted ?? {};
  const facts = [
    ex.unit_price != null ? `Giá ${ex.unit_price} ${ex.currency ?? ""}` : null,
    ex.moq ? `Tối thiểu ${ex.moq} cái` : null,
    ex.lead_days ? `Gửi sau ${ex.lead_days} ngày` : null,
    ex.shipping_note ?? null,
    ex.sample_available ? "Có bán mẫu" : null,
  ].filter(Boolean) as string[];
  return (
    <li className={cn("flex flex-col gap-2 rounded-md border p-3", out ? "ml-6 border-line bg-surface" : "mr-6 border-transparent bg-soft")}>
      <div className="flex items-center justify-between gap-2 text-[13px] text-ink-2">
        <span>
          {out ? "Chị hỏi" : "Bên bán"} · <DateTime value={m.created_at} format="relative" />
        </span>
        <Badge tone={m.status === "pending_review" ? "warning" : m.status === "sent" ? "success" : "neutral"}>{MSG_STATUS[m.status]}</Badge>
      </div>
      <p className="text-[15px] whitespace-pre-line" lang={m.language}>
        {m.body_original}
      </p>
      {m.body_vi ? (
        <p className="border-t border-line pt-2 text-[14px] whitespace-pre-line text-ink-2">
          <span className="font-medium text-ink">Dịch: </span>
          {m.body_vi}
        </p>
      ) : null}
      {facts.length ? (
        <div className="flex flex-wrap gap-1.5">
          {facts.map((f) => (
            <Badge key={f} tone="accent">
              {f}
            </Badge>
          ))}
        </div>
      ) : null}
      {out ? (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="ghost"
            icon={<Copy className="size-4" aria-hidden />}
            onClick={async () => {
              await navigator.clipboard.writeText(m.body_original);
              notifySuccess("Đã chép tin");
            }}
          >
            Chép
          </Button>
          {m.status === "pending_review" && m.approval_item_id && user?.role === "owner" ? (
            <Button size="sm" icon={<Check className="size-4" aria-hidden />} loading={approve.isPending} onClick={() => approve.mutate({ id: m.approval_item_id! })}>
              Duyệt tin
            </Button>
          ) : null}
          {m.status === "approved" ? (
            <Button size="sm" variant="secondary" icon={<Send className="size-4" aria-hidden />} loading={sent.isPending} onClick={() => sent.mutate(m.id)}>
              Đã gửi
            </Button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function InquirySheet({ supplierId, open, onClose }: { supplierId: string; open: boolean; onClose: () => void }) {
  const draft = useDraftInquiry(supplierId);
  const [topics, setTopics] = useState<InquiryTopic[]>(["price", "moq", "lead_time"]);
  const [qty, setQty] = useState("100");
  const [extra, setExtra] = useState("");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="AI soạn tin hỏi"
      description="AI viết bằng ngôn ngữ của bên bán, kèm bản dịch. Chị duyệt rồi gửi."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            disabled={!topics.length && !extra.trim()}
            loading={draft.isPending}
            onClick={async () => {
              await draft.mutateAsync({ topics, quantity: Number(qty) || null, extra: extra.trim() || undefined });
              notifySuccess("AI đã soạn tin, chị xem rồi duyệt");
              onClose();
            }}
          >
            Soạn tin
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Hỏi về</p>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(TOPIC_LABELS) as InquiryTopic[]).map((t) => (
              <Chip key={t} selected={topics.includes(t)} onClick={() => setTopics((xs) => (xs.includes(t) ? xs.filter((x) => x !== t) : [...xs, t]))}>
                {TOPIC_LABELS[t]}
              </Chip>
            ))}
          </div>
        </div>
        <Input label="Số lượng định đặt" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))} trailing="cái" />
        <Textarea label="Hỏi thêm (tiếng Việt)" value={extra} onChange={(e) => setExtra(e.target.value)} rows={2} placeholder="Ví dụ: có màu xanh rêu không?" />
      </div>
    </Sheet>
  );
}

function ReplySheet({ supplierId, open, onClose }: { supplierId: string; open: boolean; onClose: () => void }) {
  const reply = useRecordReply(supplierId);
  const [body, setBody] = useState("");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Dán câu trả lời của bên bán"
      description="AI dịch và rút giá, số lượng tối thiểu, thời gian gửi."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button
            disabled={!body.trim()}
            loading={reply.isPending}
            onClick={async () => {
              await reply.mutateAsync({ body_original: body.trim() });
              setBody("");
              notifySuccess("Đã dịch câu trả lời");
              onClose();
            }}
          >
            Dịch
          </Button>
        </>
      }
    >
      <Textarea aria-label="Câu trả lời" value={body} onChange={(e) => setBody(e.target.value)} rows={5} placeholder="亲，100件单价28元…" />
    </Sheet>
  );
}
