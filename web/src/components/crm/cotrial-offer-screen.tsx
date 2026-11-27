"use client";

import { Copy, Star } from "lucide-react";
import Link from "next/link";
import {
  Badge,
  Button,
  Card,
  DataList,
  DateTime,
  EmptyState,
  ImageBox,
  Money,
  PageHeader,
  SectionLabel,
  SkeletonList,
  Switch,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import {
  INVITE_STATUS_LABEL,
  WOULD_BUY_LABEL,
  useApplicationAction,
  useCotrialOffer,
  usePatchOffer,
  type ApplicationAction,
  type CotrialApplication,
  type CotrialOfferDetail,
} from "@/lib/api/crm";
import { DeskMoreMenu } from "@/components/desk/desk-more-menu";
import { relatedItems } from "@/components/desk/related-links";
import { copyLink } from "./cotrial-card";
import { HistoryLine } from "./cotrial-screen";

const TONE: Partial<Record<CotrialApplication["status"], "success" | "warning" | "danger" | "accent" | "neutral">> = {
  selected: "accent",
  paid: "accent",
  sample_sent: "accent",
  refund_proposed: "warning",
  refunded: "success",
  feedback_missed: "danger",
  declined: "neutral",
};

/** Một lời mời «Mời thử cùng»: link riêng, người đăng ký kèm lịch sử, chọn người → tiền → gửi hàng → cảm nhận → hoàn. */
export function CotrialOfferScreen({ id }: { id: string }) {
  const { data, isPending, error } = useCotrialOffer(id);
  const patch = usePatchOffer();
  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader loading backHref="/desk/khach/dung-thu" />
        <SkeletonList rows={3} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được lời mời" backHref="/desk/khach/dung-thu" />
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      </div>
    );
  }
  const o = data;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={o.title}
        eyebrow="Mời thử cùng"
        backHref="/desk/khach/dung-thu"
        actions={
          <>
            <Button size="sm" variant="secondary" icon={<Copy className="size-4" aria-hidden />} onClick={() => copyLink(o.link)}>
              Chép link
            </Button>
            <DeskMoreMenu items={relatedItems([{ href: `/desk/ban-chon/${o.candidate_id}`, label: "Bàn chọn" }])} />
          </>
        }
      />
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Card className="flex flex-col gap-3">
          {o.photo_urls.length ? (
            <div className="grid grid-cols-4 gap-2">
              {o.photo_urls.map((u, i) => (
                <ImageBox key={u} src={u} alt={`Ảnh lời mời ${i + 1}`} />
              ))}
            </div>
          ) : null}
          {o.description ? <p className="text-[14.5px] [text-wrap:pretty]">{o.description}</p> : null}
          <DataList
            items={[
              { label: "Giá người thử trả", value: <Money value={o.price_vnd} /> },
              { label: "Hoàn khi gửi đủ cảm nhận", value: <Money value={o.refund_amount_vnd} /> },
              { label: "Hạn cảm nhận", value: `${o.feedback_days} ngày sau khi gửi hàng` },
              { label: "Đã chọn", value: `${o.taken}/${o.slots} người` },
            ]}
          />
          <Switch
            label="Đang nhận đăng ký"
            checked={o.status === "open"}
            disabled={patch.isPending}
            onChange={(v) => patch.mutate({ id: o.id, status: v ? "open" : "closed" })}
          />
        </Card>
        <section className="flex flex-col gap-2" aria-label="Người đăng ký">
          <SectionLabel>Người đăng ký · {o.applications.length}</SectionLabel>
          {o.applications.length === 0 ? (
            <p className="text-[14px] text-ink-2">Chưa có ai đăng ký.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {o.applications.map((a) => (
                <li key={a.id}>
                  <ApplicationRow a={a} o={o} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

const NEXT: Partial<Record<CotrialApplication["status"], { action: ApplicationAction; label: string }[]>> = {
  applied: [
    { action: "select", label: "Chọn người này" },
    { action: "decline", label: "Không chọn" },
  ],
  declined: [{ action: "select", label: "Chọn lại" }],
  selected: [
    { action: "paid", label: "Đã nhận tiền" },
    { action: "decline", label: "Bỏ chọn" },
  ],
  paid: [{ action: "shipped", label: "Đã gửi hàng" }],
  feedback_received: [{ action: "propose_refund", label: "Đề xuất hoàn tiền lại" }],
};

function ApplicationRow({ a, o }: { a: CotrialApplication; o: CotrialOfferDetail }) {
  const act = useApplicationAction();
  const confirm = useConfirm();
  async function run(action: ApplicationAction) {
    let override = false;
    if (action === "select" && a.excluded) {
      override = await confirm({
        title: "Vẫn chọn người này?",
        message: a.excluded_reason ?? "Người này đang bị loại trừ vì lỡ hạn gửi cảm nhận lần trước.",
        confirmLabel: "Vẫn chọn",
      });
      if (!override) return;
    }
    try {
      await act.mutateAsync({ id: a.id, action, override });
      notifySuccess(action === "select" ? "Đã chọn và nhắn người dùng thử" : "Đã cập nhật");
    } catch (e) {
      notifyError(e);
    }
  }
  const fa = a.feedback_answers;
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/desk/khach/so-khach/${a.customer_id}`} className="text-[15px] font-semibold hover:underline">
          {a.customer_name ?? "Chưa có tên"}
        </Link>
        <Badge tone={TONE[a.status] ?? "neutral"}>{INVITE_STATUS_LABEL[a.status]}</Badge>
      </div>
      <HistoryLine h={a.history} />
      {a.excluded ? <p className="text-[13px] text-seal">Đang loại trừ: {a.excluded_reason ?? "lỡ hạn trước đây"}</p> : null}
      {a.note ? <p className="text-[14px] text-ink-2">«{a.note}»</p> : null}
      <p className="text-[12.5px] text-ink-3">
        {a.phone ?? a.email ?? ""} · đăng ký <DateTime value={a.applied_at} format="date" />
        {a.feedback_due_at && a.status === "sample_sent" ? (
          <>
            {" "}
            · hạn cảm nhận <DateTime value={a.feedback_due_at} format="date" />
          </>
        ) : null}
      </p>
      {a.feedback_at ? (
        <blockquote className="flex flex-col gap-1 border-l-2 border-accent pl-2.5 text-[14.5px]">
          {a.feedback_rating ? (
            <span className="flex items-center gap-0.5 text-review" aria-label={`${a.feedback_rating} trên 5 sao`}>
              {Array.from({ length: 5 }, (_, k) => (
                <Star key={k} className="size-3.5" aria-hidden fill={k < a.feedback_rating! ? "currentColor" : "none"} />
              ))}
            </span>
          ) : null}
          {fa.liked ? <span>Thích: {fa.liked}</span> : null}
          {fa.disliked ? <span>Chưa ưng: {fa.disliked}</span> : null}
          {fa.would_buy ? (
            <span>
              Giá <Money value={fa.ask_price_vnd ?? o.price_vnd} />: {WOULD_BUY_LABEL[fa.would_buy]}
            </span>
          ) : null}
          {fa.refund_account ? <span className="text-[13px] text-ink-2">Nhận hoàn: {fa.refund_account}</span> : null}
          {a.feedback_photo_urls.length ? (
            <span className="mt-1 grid grid-cols-4 gap-2">
              {a.feedback_photo_urls.map((u, i) => (
                <a key={u} href={u} target="_blank" rel="noreferrer">
                  <ImageBox src={u} alt={`Ảnh người dùng thử ${i + 1}`} />
                </a>
              ))}
            </span>
          ) : null}
        </blockquote>
      ) : null}
      {a.status === "refund_proposed" && a.refund_approval_id ? (
        <p className="text-[13.5px]">
          Chờ chị chuyển hoàn <Money value={a.refund_vnd ?? o.refund_amount_vnd} /> rồi duyệt ở{" "}
          <Link href="/desk/duyet" className="text-accent hover:underline">
            Hàng chờ duyệt
          </Link>
          .
        </p>
      ) : null}
      {a.status === "refunded" ? (
        <p className="text-[13.5px] text-ink-2">
          Đã hoàn <Money value={a.refund_vnd ?? 0} />
          {a.refunded_at ? (
            <>
              {" "}
              ngày <DateTime value={a.refunded_at} format="date" />
            </>
          ) : null}
        </p>
      ) : null}
      {NEXT[a.status]?.length ? (
        <div className="flex flex-wrap gap-1.5">
          {NEXT[a.status]!.map((n, i) => (
            <Button key={n.action} size="sm" variant={i === 0 ? "secondary" : "ghost"} loading={act.isPending && act.variables?.action === n.action} onClick={() => run(n.action)}>
              {n.label}
            </Button>
          ))}
        </div>
      ) : null}
    </Card>
  );
}
