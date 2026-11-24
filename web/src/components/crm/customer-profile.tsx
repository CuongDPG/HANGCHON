"use client";

import { Gift, Pin, PinOff, Plus, RefreshCw, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DateTime,
  EmptyState,
  IconButton,
  InlineSelect,
  Input,
  LevelTag,
  Money,
  PageHeader,
  SectionLabel,
  Skeleton,
  SkeletonList,
  StatTile,
  Switch,
  Textarea,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import {
  INVITE_STATUS_LABEL,
  REMINDER_STATUS_LABEL,
  useAddNote,
  useAddTag,
  useCreateReferral,
  useCustomer,
  useDeleteNote,
  useEditNote,
  useOptOut,
  useRefreshSummary,
  useRemoveTag,
  type CustomerNote,
  type CustomerProfile,
} from "@/lib/api/crm";
import { CHANNEL_LABEL } from "@/lib/api/inbox";

const NOTE_KINDS: { value: Exclude<CustomerNote["kind"], "ai_summary">; label: string }[] = [
  { value: "note", label: "Ghi chú" },
  { value: "preference", label: "Thích / không thích" },
  { value: "interest", label: "Quan tâm" },
  { value: "issue", label: "Từng gặp vấn đề" },
];
const KIND_LABEL: Record<string, string> = Object.fromEntries(NOTE_KINDS.map((k) => [k.value, k.label]));
const HIDDEN_TAGS = new Set(["tu-choi-nhan-tin"]);

/** Hồ sơ một khách (h4): AI tóm tắt, đã mua, đã hỏi, ghi chú và nhãn của chị, mã giới thiệu, nhắc mua lại. */
export function CustomerProfileScreen({ id }: { id: string }) {
  const { data: c, isPending, error, refetch } = useCustomer(id);
  if (isPending) {
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Đang tải">
        <PageHeader title="Khách" backHref="/desk/khach/so-khach" />
        <Skeleton className="h-24 w-full" />
        <SkeletonList rows={3} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Khách" backHref="/desk/khach/so-khach" />
        <EmptyState
          tone="error"
          title="Chưa mở được hồ sơ khách"
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
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        backHref="/desk/khach/so-khach"
        title={c.name || c.phone || "Khách"}
        description={[c.phone, c.email, ...c.identities.map((i) => CHANNEL_LABEL[i.channel] ?? i.channel)].filter(Boolean).join(" · ")}
      />
      <Summary c={c} />
      <div className="grid grid-cols-3 gap-2">
        <StatTile value={String(c.order_count)} label="đơn" />
        <StatTile value={<Money value={c.total_spent_vnd} compact />} label="đã mua" />
        <StatTile value={c.last_order_at ? <DateTime value={c.last_order_at} format="dayMonth" /> : "—"} label="đơn gần nhất" />
      </div>
      <div className="grid gap-5 md:grid-cols-2 md:items-start">
        <div className="flex flex-col gap-5">
          <Tags c={c} />
          <Notes c={c} />
        </div>
        <div className="flex flex-col gap-5">
          <Orders c={c} />
          <Questions c={c} />
          <Extras c={c} />
        </div>
      </div>
    </div>
  );
}

function Summary({ c }: { c: CustomerProfile }) {
  const refresh = useRefreshSummary();
  return (
    <Card tone="soft" className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <LevelTag level="auto" size="sm">
          AI tóm tắt
        </LevelTag>
        <Button size="sm" variant="ghost" icon={<RefreshCw className="size-4" />} loading={refresh.isPending} onClick={() => refresh.mutate(c.id)}>
          Tóm tắt lại
        </Button>
      </div>
      <p className="text-[15px] leading-relaxed [text-wrap:pretty]">{c.summary || "Chưa có tóm tắt. Khi khách nhắn tin hoặc có đơn, AI sẽ ghi lại."}</p>
      {c.interests.length ? (
        <div className="flex flex-wrap gap-1.5">
          {c.interests.map((i) => (
            <Badge key={i} tone="outline">
              {i}
            </Badge>
          ))}
        </div>
      ) : null}
      {c.summary_updated_at ? (
        <p className="text-[12.5px] text-ink-2">
          Cập nhật <DateTime value={c.summary_updated_at} format="relative" />
        </p>
      ) : null}
    </Card>
  );
}

function Tags({ c }: { c: CustomerProfile }) {
  const add = useAddTag();
  const remove = useRemoveTag(c.id);
  const optOut = useOptOut();
  const [tag, setTag] = useState("");
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Nhãn</SectionLabel>
      <div className="flex flex-wrap gap-1.5">
        {c.tags.filter((t) => !HIDDEN_TAGS.has(t)).length === 0 ? <span className="text-[14px] text-ink-2">Chưa có nhãn.</span> : null}
        {c.tags
          .filter((t) => !HIDDEN_TAGS.has(t))
          .map((t) => (
            <span key={t} className="inline-flex h-7 items-center gap-1 rounded-sm bg-soft pr-1 pl-2 text-[13px] text-ink-2">
              {t}
              <button type="button" aria-label={`Bỏ nhãn ${t}`} className="rounded-sm p-0.5 hover:bg-soft-2" onClick={() => remove.mutate(t)}>
                <X className="size-3.5" aria-hidden />
              </button>
            </span>
          ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!tag.trim()) return;
          await add.mutateAsync({ customerId: c.id, tag });
          setTag("");
        }}
      >
        <Input aria-label="Nhãn mới" placeholder="Thêm nhãn, vd. mua làm quà" value={tag} onChange={(e) => setTag(e.target.value)} wrapperClassName="flex-1" />
        <IconButton label="Thêm nhãn" variant="secondary" icon={<Plus />} type="submit" disabled={!tag.trim() || add.isPending} />
      </form>
      <Switch
        label="Từ chối nhận tin"
        description="Không gửi tin báo đợt, nhắc mua lại hay mời thử hàng cho khách này."
        checked={c.opted_out}
        onChange={(v) => optOut.mutate({ customerId: c.id, optOut: v })}
        disabled={optOut.isPending}
      />
    </section>
  );
}

function Notes({ c }: { c: CustomerProfile }) {
  const add = useAddNote(c.id);
  const edit = useEditNote(c.id);
  const del = useDeleteNote(c.id);
  const confirm = useConfirm();
  const [body, setBody] = useState("");
  const [kind, setKind] = useState<(typeof NOTE_KINDS)[number]["value"]>("note");
  const notes = c.notes.filter((n) => !(n.kind === "interest" && n.source === "ai"));
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Ghi chú của chị</SectionLabel>
      {notes.length === 0 ? <p className="text-[14px] text-ink-2">Chưa có ghi chú.</p> : null}
      <ul className="flex flex-col gap-2">
        {notes.map((n) => (
          <li key={n.id}>
            <Card className="flex items-start gap-2 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-[12.5px] text-ink-2">
                  {KIND_LABEL[n.kind] ?? "Ghi chú"} · <DateTime value={n.created_at} format="date" />
                </p>
                <p className="text-[15px] [text-wrap:pretty]">{n.body}</p>
              </div>
              <IconButton
                size="sm"
                label={n.pinned ? "Bỏ ghim" : "Ghim lên đầu"}
                icon={n.pinned ? <PinOff /> : <Pin />}
                onClick={() => edit.mutate({ id: n.id, pinned: !n.pinned })}
              />
              <IconButton
                size="sm"
                label="Xoá ghi chú"
                icon={<Trash2 />}
                onClick={async () => {
                  if (await confirm({ title: "Xoá ghi chú này?", confirmLabel: "Xoá", tone: "danger" })) del.mutate(n.id);
                }}
              />
            </Card>
          </li>
        ))}
      </ul>
      <form
        className="flex flex-col gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!body.trim()) return;
          await add.mutateAsync({ body, kind });
          setBody("");
          notifySuccess("Đã ghi vào sổ");
        }}
      >
        <Textarea aria-label="Ghi chú mới" placeholder="Ghi lại điều cần nhớ về khách…" value={body} onChange={(e) => setBody(e.target.value)} rows={2} />
        <div className="flex items-center gap-2">
          <InlineSelect aria-label="Loại ghi chú" value={kind} onChange={setKind} options={NOTE_KINDS} className="flex-1" />
          <Button type="submit" size="sm" loading={add.isPending} disabled={!body.trim()}>
            Lưu
          </Button>
        </div>
      </form>
    </section>
  );
}

function Orders({ c }: { c: CustomerProfile }) {
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Đã mua</SectionLabel>
      {c.orders.length === 0 ? (
        <p className="text-[14px] text-ink-2">Chưa có đơn.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {c.orders.map((o) => (
            <li key={o.id} className="flex items-start justify-between gap-3 px-3 py-2.5">
              <span className="min-w-0">
                <span className="block text-[14.5px] [text-wrap:pretty]">{o.items.map((i) => `${i.name} × ${i.quantity}`).join(", ")}</span>
                <span className="block text-[12.5px] text-ink-2">
                  {o.code} · <DateTime value={o.placed_at} format="date" /> · {o.status_label}
                </span>
              </span>
              <Money value={o.total_vnd} className="shrink-0 text-[14px] font-semibold" />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Questions({ c }: { c: CustomerProfile }) {
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Đã hỏi</SectionLabel>
      {c.recent_questions.length === 0 ? (
        <p className="text-[14px] text-ink-2">Chưa nhắn tin lần nào.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {c.recent_questions.map((q, i) => (
            <li key={i}>
              <Link href={`/desk/khach/hoi-thoai/${q.thread_id}`} className="block rounded-md border border-line bg-surface px-3 py-2 hover:border-ink-3">
                <span className="line-clamp-2 text-[14.5px]">{q.body}</span>
                <span className="text-[12.5px] text-ink-2">
                  <DateTime value={q.sent_at} format="relative" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Extras({ c }: { c: CustomerProfile }) {
  const referral = useCreateReferral();
  return (
    <>
      <Card className="flex flex-col gap-2">
        <CardHeader title="Giới thiệu bạn" aside={<Gift className="size-4 text-ink-2" aria-hidden />} />
        {c.referral ? (
          <p className="text-[14.5px]">
            Mã <span className="font-mono font-semibold tracking-wide">{c.referral.code}</span> · {c.referral.uses_count} người dùng mã
          </p>
        ) : (
          <Button size="sm" variant="secondary" className="self-start" loading={referral.isPending} onClick={() => referral.mutate(c.id)}>
            Tạo mã giới thiệu
          </Button>
        )}
      </Card>
      {c.reminders.length ? (
        <section className="flex flex-col gap-2">
          <SectionLabel>Nhắc mua lại</SectionLabel>
          {c.reminders.map((r) => (
            <p key={r.id} className="text-[14px] text-ink-2">
              {r.product_name} · <DateTime value={r.due_on} format="date" /> · {REMINDER_STATUS_LABEL[r.status]}
            </p>
          ))}
        </section>
      ) : null}
      {c.invites.length ? (
        <section className="flex flex-col gap-2">
          <SectionLabel>Thử hàng cùng chị</SectionLabel>
          {c.invites.map((i) => (
            <p key={i.id} className="text-[14px] text-ink-2">
              {i.candidate_title} · {INVITE_STATUS_LABEL[i.status]}
            </p>
          ))}
        </section>
      ) : null}
    </>
  );
}
