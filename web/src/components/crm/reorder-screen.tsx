"use client";

import { AlarmClock, CalendarClock, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DateTime,
  EmptyState,
  Input,
  LevelTag,
  PageHeader,
  SectionLabel,
  SkeletonList,
  Switch,
  Tabs,
  Textarea,
  notifySuccess,
} from "@/components/ui";
import {
  REMINDER_STATUS_LABEL,
  useReminders,
  useReorderRules,
  useRunDue,
  useSendReminder,
  useSetReorderRule,
  useSkipReminder,
  type Reminder,
  type ReorderRule,
} from "@/lib/api/crm";
import { KhachNav } from "./khach-nav";

type Tab = "pending_review" | "scheduled" | "sent" | "skipped";

/** Nhắc mua lại đúng lúc (h6): món tiêu hao sắp hết thì AI soạn tin riêng từng khách, chị duyệt rồi gửi. */
export function ReorderScreen() {
  const [tab, setTab] = useState<Tab>("pending_review");
  const all = useReminders();
  const runDue = useRunDue();
  const counts = (s: Reminder["status"]) => all.data?.filter((r) => r.status === s).length;
  const rows = all.data?.filter((r) => (tab === "sent" ? r.status === "sent" || r.status === "converted" : r.status === tab)) ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Nhắc mua lại"
        actions={
          <Button
            size="sm"
            variant="secondary"
            icon={<AlarmClock className="size-4" />}
            loading={runDue.isPending}
            onClick={async () => {
              const r = await runDue.mutateAsync();
              notifySuccess(r.drafted || r.skipped ? `AI soạn ${r.drafted} tin, bỏ qua ${r.skipped}` : "Chưa có món nào tới hạn");
            }}
          >
            Kiểm tra
          </Button>
        }
      />
      <KhachNav active="reorder" />
      <Tabs
        aria-label="Trạng thái nhắc"
        value={tab}
        onChange={setTab}
        items={[
          { value: "pending_review", label: "Chờ chị", count: counts("pending_review") },
          { value: "scheduled", label: "Sắp tới", count: counts("scheduled") },
          { value: "sent", label: "Đã nhắc", count: (counts("sent") ?? 0) + (counts("converted") ?? 0) },
          { value: "skipped", label: "Bỏ qua", count: counts("skipped") },
        ]}
      />
      {all.isPending ? (
        <SkeletonList rows={3} />
      ) : all.error ? (
        <EmptyState tone="error" title="Chưa tải được danh sách nhắc" description={all.error.message} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<CalendarClock />}
          title={tab === "pending_review" ? "Không có tin nhắc nào chờ chị" : "Chưa có gì ở đây"}
          description="Khi khách nhận món tiêu hao, hệ thống tự tính ngày sắp hết. Tới hạn, AI soạn tin nhắc để chị duyệt."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((r) => (
            <li key={r.id}>
              <ReminderCard r={r} />
            </li>
          ))}
        </ul>
      )}
      <Rules />
      <p className="text-[13.5px] text-ink-2">
        Khách từ chối nhận tin không bao giờ được nhắc.{" "}
        <Link href="/desk/khach/so-khach" className="text-accent underline underline-offset-2">
          Xem trong Sổ khách
        </Link>
      </p>
    </div>
  );
}

function ReminderCard({ r }: { r: Reminder }) {
  const send = useSendReminder();
  const skip = useSkipReminder();
  const [body, setBody] = useState<string | null>(null);
  const pending = r.status === "pending_review";
  return (
    <Card tone={pending ? "accent" : "default"} className="flex flex-col gap-2">
      <CardHeader
        title={
          <>
            {r.customer_name ?? "Khách"} · {r.product_name}
          </>
        }
        aside={<Badge tone={r.status === "converted" ? "success" : pending ? "warning" : "neutral"}>{REMINDER_STATUS_LABEL[r.status]}</Badge>}
      />
      <p className="text-[13.5px] text-ink-2">
        Tới hạn <DateTime value={r.due_on} format="date" />
        {r.reason ? ` · ${r.reason}` : ""}
      </p>
      {r.message_body ? (
        body !== null ? (
          <Textarea aria-label="Tin nhắc" value={body} onChange={(e) => setBody(e.target.value)} rows={3} />
        ) : (
          <div className="rounded-md bg-review-wash/60 p-3">
            {pending ? (
              <LevelTag level="review" size="sm" className="mb-1.5">
                AI soạn
              </LevelTag>
            ) : null}
            <p className="text-[14.5px] leading-relaxed [text-wrap:pretty]">{r.message_body}</p>
          </div>
        )
      ) : null}
      {pending || r.status === "scheduled" ? (
        <div className="flex flex-wrap gap-2">
          {pending ? (
            <>
              {body === null ? (
                <Button size="sm" variant="secondary" onClick={() => setBody(r.message_body ?? "")}>
                  Sửa
                </Button>
              ) : null}
              <Button
                size="sm"
                icon={<Send className="size-4" />}
                loading={send.isPending}
                onClick={async () => {
                  await send.mutateAsync({ id: r.id, body: body ?? undefined });
                  setBody(null);
                  notifySuccess(`Đã nhắn ${r.customer_name ?? "khách"}`);
                }}
              >
                Gửi
              </Button>
            </>
          ) : null}
          <Button size="sm" variant="ghost" loading={skip.isPending} onClick={() => skip.mutate(r.id)}>
            Bỏ qua lần này
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

function Rules() {
  const { data, isPending, error } = useReorderRules();
  return (
    <section className="flex flex-col gap-2.5">
      <SectionLabel>Chu kỳ dùng của món tiêu hao</SectionLabel>
      {isPending ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được chu kỳ" description={error.message} />
      ) : data.length === 0 ? (
        <p className="text-[14px] text-ink-2">Chưa có món tiêu hao nào. Đánh dấu món tiêu hao ở trang Sản phẩm.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {data.map((rule) => (
            <li key={rule.product_id} className="px-3 py-2.5">
              <RuleRow rule={rule} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RuleRow({ rule }: { rule: ReorderRule }) {
  const set = useSetReorderRule();
  const fallback = rule.product_days ?? rule.category_days;
  const [days, setDays] = useState(rule.configured_days ? String(rule.configured_days) : "");
  const dirty = days !== (rule.configured_days ? String(rule.configured_days) : "");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block text-[15px] font-medium">{rule.name}</span>
          <span className="block text-[13px] text-ink-2">
            {rule.effective_days ? `Nhắc sau khoảng ${rule.effective_days} ngày` : "Không nhắc"}
            {fallback && !rule.configured_days ? " (theo sản phẩm / nhóm hàng)" : ""}
          </span>
        </span>
        <Switch
          label={<span className="sr-only">Nhắc món này</span>}
          checked={rule.active && !!rule.effective_days}
          onChange={(on) => set.mutate({ productId: rule.product_id, cycleDays: rule.configured_days ?? fallback ?? 30, active: on })}
          className="shrink-0 py-0"
        />
      </div>
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          set.mutate(
            { productId: rule.product_id, cycleDays: days ? Number(days) : null, active: true },
            { onSuccess: () => notifySuccess("Đã lưu chu kỳ") },
          );
        }}
      >
        <Input
          aria-label={`Số ngày dùng hết ${rule.name}`}
          inputMode="numeric"
          placeholder={fallback ? String(fallback) : "Số ngày"}
          value={days}
          onChange={(e) => setDays(e.target.value.replace(/\D/g, "").slice(0, 3))}
          trailing="ngày"
          wrapperClassName="w-36"
        />
        <Button type="submit" size="sm" variant="secondary" disabled={!dirty} loading={set.isPending}>
          Lưu
        </Button>
      </form>
    </div>
  );
}
