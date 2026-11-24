"use client";

import { Copy, MessagesSquare, Send, Sparkles, UsersRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DateTime,
  EmptyState,
  InlineSelect,
  Input,
  LevelTag,
  Money,
  PageHeader,
  SectionLabel,
  Sheet,
  SkeletonList,
  Textarea,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import {
  useBroadcasts,
  useCancelBroadcast,
  useCreateBroadcast,
  useCreateDigest,
  useDigests,
  useRegulars,
  useSendBroadcast,
  useUpdateRegularThreshold,
  type Broadcast,
  type GroupDigest,
} from "@/lib/api/crm";
import { KhachNav } from "./khach-nav";

const STATUS: Record<Broadcast["status"], { label: string; tone: "warning" | "success" | "neutral" | "danger" }> = {
  draft: { label: "Nháp", tone: "neutral" },
  pending_review: { label: "Chờ chị duyệt", tone: "warning" },
  approved: { label: "Đã duyệt", tone: "neutral" },
  scheduled: { label: "Đã hẹn giờ", tone: "neutral" },
  sending: { label: "Đang gửi", tone: "neutral" },
  sent: { label: "Đã gửi", tone: "success" },
  failed: { label: "Gửi lỗi", tone: "danger" },
  cancelled: { label: "Đã huỷ", tone: "neutral" },
};

/** Nhóm khách quen (h5): danh sách theo tiêu chí, tin báo đợt mới AI soạn, tóm tắt thảo luận nhóm Zalo. */
export function RegularsScreen() {
  const regulars = useRegulars();
  const [composeOpen, setComposeOpen] = useState(false);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Khách quen"
        description={regulars.data ? `${regulars.data.total} khách · ${regulars.data.reachable} khách nhận được tin` : " "}
      />
      <KhachNav active="regulars" />
      <Broadcasts onCompose={() => setComposeOpen(true)} />
      <Digest />
      <section className="flex flex-col gap-2.5">
        <SectionLabel aside={regulars.data ? <Threshold value={regulars.data.min_orders} /> : null}>Danh sách khách quen</SectionLabel>
        {regulars.isPending ? (
          <SkeletonList rows={3} />
        ) : regulars.error ? (
          <EmptyState tone="error" title="Chưa tải được danh sách" description={regulars.error.message} />
        ) : regulars.data.items.length === 0 ? (
          <EmptyState icon={<UsersRound />} title="Chưa có khách quen" description="Khách mua đủ số đơn theo tiêu chí sẽ hiện ở đây." />
        ) : (
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {regulars.data.items.map((c) => (
              <li key={c.id}>
                <Link href={`/desk/khach/so-khach/${c.id}`} className="flex items-center justify-between gap-3 px-3 py-2.5 hover:bg-soft-2">
                  <span className="min-w-0">
                    <span className="block truncate text-[15px] font-medium">{c.name || c.phone}</span>
                    <span className="block truncate text-[13px] text-ink-2">{c.summary ?? c.phone}</span>
                  </span>
                  <span className="shrink-0 text-right text-[13px] text-ink-2">
                    {c.opted_out ? (
                      <Badge tone="danger">Không nhận tin</Badge>
                    ) : (
                      <>
                        <span className="block font-semibold text-ink">{c.order_count} đơn</span>
                        <Money value={c.total_spent_vnd} compact />
                      </>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <ComposeSheet open={composeOpen} onClose={() => setComposeOpen(false)} />
    </div>
  );
}

function Threshold({ value }: { value: number }) {
  const update = useUpdateRegularThreshold();
  return (
    <InlineSelect
      appearance="inline"
      aria-label="Tiêu chí khách quen"
      value={String(value)}
      onChange={(v) => update.mutate(Number(v), { onSuccess: () => notifySuccess("Đã đổi tiêu chí khách quen") })}
      options={[1, 2, 3, 4, 5, 6].map((n) => ({ value: String(n), label: `Từ ${n} đơn` }))}
    />
  );
}

function Broadcasts({ onCompose }: { onCompose: () => void }) {
  const { data, isPending, error } = useBroadcasts();
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel
        aside={
          <Button size="sm" variant="ghost" icon={<Sparkles className="size-4" />} onClick={onCompose}>
            Soạn tin
          </Button>
        }
      >
        Tin cho khách quen
      </SectionLabel>
      {isPending ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được tin" description={error.message} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<MessagesSquare />}
          title="Chưa có tin nào"
          description="Khi mở đợt mới, AI soạn sẵn tin báo cho khách quen để chị xem rồi gửi."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((b) => (
            <li key={b.id}>
              <BroadcastCard b={b} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BroadcastCard({ b }: { b: Broadcast }) {
  const send = useSendBroadcast();
  const cancel = useCancelBroadcast();
  const confirm = useConfirm();
  const [body, setBody] = useState<string | null>(null);
  const pending = b.status === "pending_review" || b.status === "draft" || b.status === "failed";
  const st = STATUS[b.status];

  async function copy() {
    try {
      await navigator.clipboard.writeText(b.body);
      notifySuccess("Đã chép, chị dán vào nhóm Zalo nhé");
    } catch {
      notifyError("Trình duyệt không cho chép, chị bôi đen để chép giúp em.");
    }
  }

  return (
    <Card tone={pending ? "accent" : "default"} className="flex flex-col gap-2.5">
      <CardHeader title={b.title} aside={<Badge tone={st.tone}>{st.label}</Badge>} />
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
        {b.ai_generated ? <LevelTag level="review" size="sm">AI soạn</LevelTag> : null}
        {b.drop_title ? <span>{b.drop_title}</span> : null}
        <span>
          {b.status === "sent" ? `Đã tới ${b.delivered_count}/${b.recipient_count} khách` : `${b.recipient_count} khách nhận`}
        </span>
        {b.sent_at ? <DateTime value={b.sent_at} format="relative" /> : null}
      </div>
      {body !== null ? (
        <Textarea aria-label="Nội dung tin" value={body} onChange={(e) => setBody(e.target.value)} rows={5} />
      ) : (
        <p className="rounded-md bg-soft p-3 text-[14.5px] leading-relaxed whitespace-pre-line">{b.body}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" icon={<Copy className="size-4" />} onClick={copy}>
          Chép để dán vào nhóm
        </Button>
        {pending ? (
          <>
            {body === null ? (
              <Button size="sm" variant="secondary" onClick={() => setBody(b.body)}>
                Sửa
              </Button>
            ) : null}
            <Button
              size="sm"
              icon={<Send className="size-4" />}
              loading={send.isPending}
              disabled={!b.recipient_count}
              onClick={async () => {
                if (!(await confirm({ title: `Gửi tin cho ${b.recipient_count} khách quen?`, message: "Khách từ chối nhận tin sẽ không nhận.", confirmLabel: "Gửi" }))) return;
                const r = await send.mutateAsync({ id: b.id, body: body ?? undefined });
                setBody(null);
                notifySuccess(`Đã gửi ${r.delivered_count}/${r.recipient_count} khách`);
              }}
            >
              Gửi {b.recipient_count} khách
            </Button>
            <Button size="sm" variant="ghost" onClick={() => cancel.mutate(b.id)} loading={cancel.isPending}>
              Huỷ tin
            </Button>
          </>
        ) : null}
      </div>
    </Card>
  );
}

function ComposeSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateBroadcast();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Tin cho khách quen"
      description="Tin vào hàng chờ để chị xem lại lần cuối trước khi gửi hàng loạt."
      footer={
        <Button
          block
          loading={create.isPending}
          disabled={!title.trim() || !body.trim()}
          onClick={async () => {
            await create.mutateAsync({ title, body });
            setTitle("");
            setBody("");
            onClose();
            notifySuccess("Đã tạo tin, chờ chị gửi");
          }}
        >
          Tạo tin
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Tiêu đề (chỉ chị thấy)" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="vd. Báo nghỉ Tết" />
        <Textarea label="Nội dung" value={body} onChange={(e) => setBody(e.target.value)} rows={5} />
      </div>
    </Sheet>
  );
}

function Digest() {
  const create = useCreateDigest();
  const { data } = useDigests();
  const [text, setText] = useState("");
  const latest = data?.[0];
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Tóm tắt nhóm Zalo</SectionLabel>
      <Card className="flex flex-col gap-2.5">
        <Textarea
          label="Dán nội dung trò chuyện trong nhóm"
          hint="Mỗi dòng dạng «Tên: nội dung». Chỉ chị xem bản tóm tắt."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
        />
        <Button
          size="sm"
          className="self-end"
          icon={<Sparkles className="size-4" />}
          loading={create.isPending}
          disabled={text.trim().length < 10}
          onClick={async () => {
            await create.mutateAsync(text);
            setText("");
            notifySuccess("AI đã tóm tắt");
          }}
        >
          Tóm tắt
        </Button>
      </Card>
      {latest ? <DigestCard d={latest} /> : null}
    </section>
  );
}

function DigestCard({ d }: { d: GroupDigest }) {
  return (
    <Card tone="soft" className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <LevelTag level="auto" size="sm">
          AI tóm tắt
        </LevelTag>
        <span className="text-[12.5px] text-ink-2">
          <DateTime value={d.created_at} format="relative" />
        </span>
      </div>
      <p className="text-[15px] [text-wrap:pretty]">{d.summary}</p>
      {d.open_questions.length ? (
        <div>
          <p className="text-[13px] font-semibold text-ink-2">Câu hỏi chưa ai trả lời</p>
          <ul className="mt-1 list-disc pl-5 text-[14.5px]">
            {d.open_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {d.highlights.length ? (
        <div>
          <p className="text-[13px] font-semibold text-ink-2">Đáng chú ý</p>
          <ul className="mt-1 list-disc pl-5 text-[14.5px]">
            {d.highlights.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {d.product_mentions.length ? (
        <div className="flex flex-wrap gap-1.5">
          {d.product_mentions.map((m) => (
            <Badge key={m.name} tone="outline">
              {m.name} · {m.count} lần
            </Badge>
          ))}
        </div>
      ) : null}
    </Card>
  );
}
