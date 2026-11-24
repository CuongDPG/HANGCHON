"use client";

import { Inbox, MessageSquarePlus, Search } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { KhachNav } from "@/components/crm/khach-nav";
import { Badge, Button, Card, DateTime, EmptyState, IconButton, Input, LevelTag, PageHeader, SkeletonList, Tabs } from "@/components/ui";
import { useInboxMeta, useThreadCounts, useThreads, type InboxTab, type ThreadItem } from "@/lib/api/inbox";
import { cn } from "@/lib/cn";
import { DraftBox } from "./draft-box";
import { SimulateSheet } from "./simulate-sheet";

/** Hộp thư gộp (h1): bình luận và tin nhắn mọi kênh ở một chỗ, AI soạn sẵn (h2), việc khó chuyển chị (h3). */
export function InboxScreen() {
  const [tab, setTab] = useState<InboxTab>("waiting");
  const [q, setQ] = useState("");
  const query = useDeferredValue(q.trim());
  const [simOpen, setSimOpen] = useState(false);
  const counts = useThreadCounts();
  const meta = useInboxMeta();
  const threads = useThreads({ tab, q: query });
  const c = counts.data;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Hộp thư"
        description={c ? (c.waiting ? `${c.waiting} tin chờ chị` : "Không có tin nào chờ chị") : " "}
        actions={
          meta.data?.simulate_enabled ? (
            <IconButton label="Giả lập tin khách gửi" variant="secondary" icon={<MessageSquarePlus />} onClick={() => setSimOpen(true)} />
          ) : null
        }
      />
      <KhachNav active="inbox" />
      <Tabs
        aria-label="Lọc hội thoại"
        value={tab}
        onChange={setTab}
        items={[
          { value: "waiting", label: "Chờ chị", count: c?.waiting },
          { value: "ai", label: "AI đã trả lời", count: c?.ai },
          { value: "all", label: "Tất cả", count: c?.all },
        ]}
      />
      <Input
        aria-label="Tìm trong hộp thư"
        placeholder="Tìm tên khách, nội dung tin…"
        leading={<Search aria-hidden />}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        type="search"
      />
      {threads.isPending ? (
        <SkeletonList rows={4} />
      ) : threads.error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được hộp thư"
          description={threads.error.message}
          action={
            <Button variant="secondary" onClick={() => threads.refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : threads.data.items.length === 0 ? (
        <EmptyState
          icon={query ? <Search /> : <Inbox />}
          title={query ? "Không thấy hội thoại nào" : tab === "waiting" ? "Không có tin nào chờ chị" : "Hộp thư đang trống"}
          description={
            query
              ? "Thử tìm không dấu, hoặc tìm ở tab «Tất cả»."
              : tab === "waiting"
                ? "Tin mới về câu khó, khiếu nại hay bản nháp AI soạn sẽ hiện ở đây."
                : "Bình luận và tin nhắn từ Facebook, Instagram, Zalo sẽ về đây."
          }
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {threads.data.items.map((t) => (
            <li key={t.id}>
              <ThreadCard thread={t} />
            </li>
          ))}
        </ul>
      )}
      <SimulateSheet open={simOpen} onClose={() => setSimOpen(false)} />
    </div>
  );
}

function ThreadCard({ thread: t }: { thread: ThreadItem }) {
  const name = t.customer_name || t.participant_name || "Khách";
  const aiReplied = t.status === "ai_handled" && t.last_message?.direction === "outbound";
  return (
    <Card tone={t.needs_owner && t.escalation_reason !== "low_confidence" ? "danger" : "default"} className="flex flex-col gap-2.5">
      <Link href={`/desk/khach/hoi-thoai/${t.id}`} className="-m-1 flex flex-col gap-1 rounded-md p-1 hover:bg-soft-2/60">
        <span className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-2">
            <ChannelBadge channel={t.channel} label={t.channel_label} />
            <span className={cn("truncate text-[15px] font-semibold", t.unread_count && "text-ink")}>{name}</span>
            {t.kind === "comment" ? <span className="shrink-0 text-[12.5px] text-ink-3">bình luận</span> : null}
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-[13px] text-ink-2">
            {t.unread_count ? <span aria-label={`${t.unread_count} tin chưa đọc`} className="size-2 rounded-full bg-accent" /> : null}
            {t.last_message_at ? <DateTime value={t.last_message_at} format="relative" /> : null}
          </span>
        </span>
        <span className="line-clamp-2 text-[15px] text-ink [text-wrap:pretty]">{t.last_inbound?.body ?? t.snippet}</span>
      </Link>
      {t.draft ? (
        <DraftBox draft={t.draft} escalationLabel={t.escalation_label} compact />
      ) : aiReplied ? (
        <div className="flex flex-col gap-1">
          <LevelTag level="auto" size="sm" className="self-start">
            AI đã trả lời{t.intent_label ? ` · ${t.intent_label.toLowerCase()}` : ""}
          </LevelTag>
          <p className="line-clamp-2 text-[14px] text-ink-2">{t.last_message?.body}</p>
        </div>
      ) : t.status === "waiting_customer" && t.last_message?.direction === "outbound" ? (
        <p className="line-clamp-2 text-[13.5px] text-ink-2">Mình đã trả lời: {t.last_message.body}</p>
      ) : t.status === "needs_owner" ? (
        <p className="text-[13px] text-ink-2">Chờ chị trả lời</p>
      ) : null}
    </Card>
  );
}

export function ChannelBadge({ channel, label }: { channel: string; label: string }) {
  const tone = channel === "facebook" ? "accent" : channel.startsWith("zalo") ? "success" : channel === "instagram" ? "warning" : "neutral";
  return (
    <Badge tone={tone} className="shrink-0">
      {label}
    </Badge>
  );
}
