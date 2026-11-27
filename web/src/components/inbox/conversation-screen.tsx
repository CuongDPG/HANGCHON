"use client";

import { Ban, CircleCheck, Link2, RefreshCw, Send, Sparkles, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CustomerPicker } from "@/components/crm/customer-picker";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  DateTime,
  EmptyState,
  Money,
  PageHeader,
  SectionLabel,
  Sheet,
  Skeleton,
  SkeletonList,
  Textarea,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { useLinkCustomer, useMarkRead, useRedraft, useReply, useThread, useThreadStatus, type InboxMessage, type ThreadDetail } from "@/lib/api/inbox";
import { cn } from "@/lib/cn";
import { DraftBox } from "./draft-box";
import { ChannelBadge } from "./inbox-screen";

/** Một hội thoại: tin qua lại, bản nháp AI (Sửa / Gửi), việc chuyển chị, ô trả lời, khách là ai. */
export function ConversationScreen({ id }: { id: string }) {
  const { data: t, isPending, error, refetch } = useThread(id);
  const markRead = useMarkRead();
  const readOnce = useRef(false);

  useEffect(() => {
    if (t && t.unread_count && !readOnce.current) {
      readOnce.current = true;
      markRead.mutate(t.id);
    }
  }, [t, markRead]);

  if (isPending) {
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Đang tải">
        <PageHeader loading backHref="/desk/khach" />
        <Skeleton className="h-16 w-full" />
        <SkeletonList rows={3} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Hội thoại" backHref="/desk/khach" />
        <EmptyState
          tone="error"
          title="Chưa mở được hội thoại"
          description={error.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      </div>
    );
  }

  const name = t.customer?.name || t.participant_name || "Khách";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        backHref="/desk/khach"
        eyebrow={
          <span className="flex items-center gap-x-2">
            <ChannelBadge channel={t.channel} label={t.channel_label} />
            <span className="whitespace-nowrap">{t.kind === "comment" ? "Bình luận công khai" : "Tin nhắn riêng"}</span>
            {t.account_name ? <span className="hidden text-ink-3 md:inline">· {t.account_name}</span> : null}
          </span>
        }
        title={name}
      />
      <div className="grid gap-4 md:grid-cols-[1fr_17rem] md:items-start">
        <div className="flex min-w-0 flex-col gap-4">
          <Messages messages={t.messages} customerName={name} />
          {t.draft ? (
            <Card tone={t.draft.kind === "escalation" ? "danger" : "default"}>
              <DraftBox draft={t.draft} escalationLabel={t.escalation_label} />
            </Card>
          ) : null}
          <Composer thread={t} />
        </div>
        <aside className="flex flex-col gap-4">
          <CustomerCard thread={t} />
          <ThreadActions thread={t} />
        </aside>
      </div>
    </div>
  );
}

function Messages({ messages, customerName }: { messages: InboxMessage[]; customerName: string }) {
  if (!messages.length) return <EmptyState title="Chưa có tin nào" />;
  return (
    <ol className="flex flex-col gap-2.5" aria-label="Các tin trong hội thoại">
      {messages.map((m) => {
        const out = m.direction === "outbound";
        return (
          <li key={m.id} className={cn("flex flex-col gap-1", out ? "items-end" : "items-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-md px-3 py-2 text-[15px] leading-relaxed whitespace-pre-line [overflow-wrap:anywhere]",
                out ? "bg-accent-wash text-ink" : "border border-line bg-surface",
                m.status === "failed" && "border border-seal",
              )}
            >
              {m.body}
            </div>
            <span className="flex items-center gap-1.5 text-[12px] text-ink-3">
              {out ? (m.sender === "ai" ? "AI tự gửi" : m.ai_generated ? "Chị gửi · AI soạn" : "Chị gửi") : m.author_name || customerName}
              {m.extracted?.private_reply ? " · nhắn riêng" : ""}
              <span aria-hidden>·</span>
              <DateTime value={m.sent_at} format="relative" />
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Composer({ thread: t }: { thread: ThreadDetail }) {
  const reply = useReply();
  const redraft = useRedraft();
  const [body, setBody] = useState("");
  const [priv, setPriv] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const cap = t.capabilities;

  async function send() {
    await reply.mutateAsync({ threadId: t.id, body, private: priv });
    setBody("");
    notifySuccess("Đã gửi cho khách");
  }

  async function askAi() {
    await redraft.mutateAsync({ threadId: t.id, note });
    setNoteOpen(false);
    setNote("");
    notifySuccess("AI đã soạn lại");
  }

  if (!cap.can_reply) {
    return (
      <Card tone="soft">
        <p className="text-[14.5px] text-ink-2">{cap.reason}</p>
      </Card>
    );
  }
  return (
    <Card className="flex flex-col gap-2.5">
      <Textarea
        label={t.kind === "comment" && !priv ? "Trả lời công khai dưới bình luận" : "Trả lời khách"}
        placeholder="Chị gõ câu trả lời…"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={2}
        hint={cap.human_agent_tag ? "Đã quá 24 giờ từ tin cuối của khách: tin gửi kèm thẻ «người thật trả lời»." : undefined}
      />
      {cap.private_reply ? <Checkbox label="Nhắn riêng cho khách (một lần, trong 7 ngày)" checked={priv} onChange={(e) => setPriv(e.target.checked)} /> : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button size="sm" variant="ghost" icon={<Sparkles className="size-4" />} onClick={() => setNoteOpen(true)} disabled={redraft.isPending}>
          AI soạn lại
        </Button>
        <Button size="sm" icon={<Send className="size-4" />} loading={reply.isPending} disabled={!body.trim()} onClick={send}>
          Gửi
        </Button>
      </div>
      <Sheet
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        title="Nhờ AI soạn lại"
        description={t.needs_owner ? "Việc này đang chờ chị: AI chỉ soạn khi chị dặn cách trả lời." : "Dặn thêm nếu cần, vd. «nhắc đợt sắp đóng», «trả lời ngắn hơn»."}
        footer={
          <Button block loading={redraft.isPending} disabled={t.needs_owner && !note.trim()} onClick={askAi} icon={<RefreshCw className="size-4" />}>
            Soạn lại
          </Button>
        }
      >
        <Textarea aria-label="Lời dặn cho AI" value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="Lời dặn (không bắt buộc)" />
      </Sheet>
    </Card>
  );
}

function CustomerCard({ thread: t }: { thread: ThreadDetail }) {
  const link = useLinkCustomer();
  const [open, setOpen] = useState(false);
  const c = t.customer;
  return (
    <Card className="flex flex-col gap-2">
      <SectionLabel>Khách</SectionLabel>
      {c ? (
        <>
          <Link href={`/desk/khach/so-khach/${c.id}`} className="flex items-center gap-2 text-[15px] font-semibold hover:text-accent">
            <UserRound className="size-4 text-ink-2" aria-hidden />
            {c.name || c.phone}
          </Link>
          <p className="text-[13.5px] text-ink-2">
            {c.order_count ? (
              <>
                {c.order_count} đơn · <Money value={c.total_spent_vnd} />
              </>
            ) : (
              "Chưa mua đơn nào"
            )}
          </p>
          {c.is_regular ? <Badge tone="accent" className="self-start">Khách quen</Badge> : null}
        </>
      ) : (
        <p className="text-[14px] text-ink-2">Chưa nhận ra khách này trong sổ khách.</p>
      )}
      {t.product ? (
        <p className="text-[13.5px] text-ink-2">
          Đang hỏi: <span className="text-ink">{t.product.name}</span> · <Money value={t.product.price_vnd} />
        </p>
      ) : null}
      <Button size="sm" variant="secondary" icon={<Link2 className="size-4" />} onClick={() => setOpen(true)} className="self-start">
        {c ? "Đổi khách" : "Gắn với khách"}
      </Button>
      <CustomerPicker
        open={open}
        onClose={() => setOpen(false)}
        title="Gắn hội thoại với khách"
        description="Các hội thoại khác của cùng người trên kênh này cũng được gắn theo."
        onPick={async ([picked]) => {
          await link.mutateAsync({ threadId: t.id, customerId: picked.id });
          setOpen(false);
          notifySuccess(`Đã gắn với ${picked.name ?? "khách"}`);
        }}
      />
    </Card>
  );
}

function ThreadActions({ thread: t }: { thread: ThreadDetail }) {
  const setStatus = useThreadStatus();
  const confirm = useConfirm();
  if (t.status === "closed" || t.status === "spam") {
    return (
      <Button size="sm" variant="secondary" onClick={() => setStatus.mutate({ threadId: t.id, status: "open" })}>
        Mở lại hội thoại
      </Button>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="secondary"
        icon={<CircleCheck className="size-4" />}
        onClick={async () => {
          await setStatus.mutateAsync({ threadId: t.id, status: "closed" });
          notifySuccess("Đã đóng hội thoại");
        }}
      >
        Đóng hội thoại
      </Button>
      <Button
        size="sm"
        variant="ghost"
        icon={<Ban className="size-4" />}
        onClick={async () => {
          if (await confirm({ title: "Đánh dấu là tin rác?", message: "Tin mới từ hội thoại này sẽ không hiện trong hộp thư và AI không trả lời.", confirmLabel: "Là tin rác", tone: "danger" })) {
            await setStatus.mutateAsync({ threadId: t.id, status: "spam" });
            notifySuccess("Đã chuyển vào tin rác");
          }
        }}
      >
        Tin rác
      </Button>
    </div>
  );
}
