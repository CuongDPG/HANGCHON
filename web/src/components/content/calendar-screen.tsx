"use client";

import { ChevronLeft, ChevronRight, ExternalLink, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useState, type DragEvent } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  EmptyState,
  IconButton,
  Input,
  PageHeader,
  Sheet,
  SkeletonList,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import {
  useAcceptSuggestion,
  useCalendar,
  useDismissSuggestion,
  usePlanWeek,
  usePostAction,
  useReschedule,
  type CalendarDay,
  type PostCard,
  type SlotSuggestion,
} from "@/lib/api/content";
import { formatDateTime, formatDayMonth, formatTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import { ChannelMark, ContentNav, DISPLAY_STATUS, StatusBadge, toLocalInput } from "./shared";

const MOVABLE = new Set(["planned", "approved", "failed"]);

function addDays(iso: string, n: number) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  const pad = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Cùng giờ trong ngày, đổi sang ngày khác (giờ máy = giờ Việt Nam). */
function moveToDay(iso: string, day: string): string {
  const src = new Date(iso);
  const d = new Date(`${day}T00:00:00`);
  d.setHours(src.getHours(), src.getMinutes(), 0, 0);
  return d.toISOString();
}

const tone: Record<string, string> = {
  published: "border-auto/30 bg-auto-wash",
  draft_pushed: "border-review/40 bg-review-wash",
  approved: "border-accent/40 bg-accent-wash",
  pending: "border-line-strong bg-surface",
  needs_fix: "border-seal/40 bg-seal-wash",
  failed: "border-seal/40 bg-seal-wash",
  publishing: "border-accent/40 bg-accent-wash",
};

export function CalendarScreen() {
  const [week, setWeek] = useState<string | undefined>(undefined);
  const { data, isPending, error } = useCalendar(week);
  const plan = usePlanWeek();
  const reschedule = useReschedule();
  const [open, setOpen] = useState<PostCard | null>(null);
  const [dragOver, setDragOver] = useState<string | null>(null);

  function onDrop(e: DragEvent, day: CalendarDay) {
    e.preventDefault();
    setDragOver(null);
    const raw = e.dataTransfer.getData("application/json");
    if (!raw) return;
    const p = JSON.parse(raw) as { id: string; scheduled_at: string };
    const at = moveToDay(p.scheduled_at, day.day);
    if (at === new Date(p.scheduled_at).toISOString()) return;
    if (new Date(at) <= new Date()) {
      notifySuccess("Ngày này đã qua giờ đăng, chị chọn ngày khác nhé");
      return;
    }
    reschedule.mutate({ id: p.id, scheduled_at: at }, { onSuccess: () => notifySuccess(`Đã dời sang ${day.name}`) });
  }

  const counts = data?.counts ?? {};
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Lịch đăng"
        eyebrow={data?.label ?? "Tuần này"}
        actions={
          <>
            <IconButton label="Tuần trước" icon={<ChevronLeft />} onClick={() => data && setWeek(addDays(data.week_start, -7))} />
            <IconButton label="Tuần sau" icon={<ChevronRight />} onClick={() => data && setWeek(addDays(data.week_start, 7))} />
          </>
        }
      />
      <ContentNav />
      <div className="flex flex-wrap items-center gap-2">
        {(["published", "approved", "pending", "draft_pushed", "needs_fix", "failed"] as const).map((k) =>
          counts[k] || k === "published" || k === "approved" || k === "pending" ? (
            <Badge key={k} tone={DISPLAY_STATUS[k].tone}>
              {k === "draft_pushed" ? "Nháp TikTok" : DISPLAY_STATUS[k].label} {counts[k] ?? 0}
            </Badge>
          ) : null,
        )}
        <span className="flex-1" />
        <Button
          size="sm"
          variant="secondary"
          icon={<Sparkles className="size-4" aria-hidden />}
          loading={plan.isPending}
          onClick={() =>
            plan.mutate(data?.week_start, {
              onSuccess: (r) =>
                notifySuccess(
                  r.moved || r.suggested
                    ? `AI dời ${r.moved} bài, gợi ý ${r.suggested} ô trống`
                    : "Lịch tuần đã gọn, không có ô trống cần gợi ý",
                ),
            })
          }
        >
          AI xếp lịch tuần
        </Button>
      </div>

      {isPending ? (
        <SkeletonList rows={6} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được lịch" description={error.message} />
      ) : data ? (
        <>
          {/* điện thoại: danh sách theo ngày; máy tính: lưới 7 cột kéo thả */}
          <ol className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface md:hidden">
            {data.days.map((d) => (
              <li key={d.day} className="flex gap-3 px-3 py-2.5">
                <div className="w-9 shrink-0 pt-1">
                  <p className={cn("font-display text-[15px] font-bold", isToday(d.day) && "text-accent")}>{d.label}</p>
                  <p className="text-[12px] text-ink-3">{formatDayMonth(`${d.day}T12:00:00`)}</p>
                </div>
                <DayBody day={d} onOpen={setOpen} />
              </li>
            ))}
          </ol>
          <div className="hidden grid-cols-7 gap-2 md:grid">
            {data.days.map((d) => (
              <section
                key={d.day}
                aria-label={d.name}
                onDragOver={(e) => {
                  if (!d.rest) {
                    e.preventDefault();
                    setDragOver(d.day);
                  }
                }}
                onDragLeave={() => setDragOver((x) => (x === d.day ? null : x))}
                onDrop={(e) => onDrop(e, d)}
                className={cn(
                  "flex min-h-64 flex-col gap-2 rounded-md border bg-surface p-2",
                  dragOver === d.day ? "border-accent bg-accent-wash" : "border-line",
                  d.rest && "bg-soft",
                )}
              >
                <header className="flex items-baseline justify-between">
                  <span className={cn("font-display text-[15px] font-bold", isToday(d.day) && "text-accent")}>
                    {d.label}
                    {isToday(d.day) ? <span className="ml-1 text-[12px] font-medium">hôm nay</span> : null}
                  </span>
                  <span className="text-[12px] text-ink-3">{formatDayMonth(`${d.day}T12:00:00`)}</span>
                </header>
                <DayBody day={d} onOpen={setOpen} draggable />
              </section>
            ))}
          </div>
          <p className="text-[13px] text-ink-2">
            Giờ đăng chọn theo lúc khách của chị hay xem:{" "}
            {data.best_times.map((b) => `${b.channel_label} ${b.time}`).join(" · ")}
            {data.best_times.every((b) => b.source === "default") ? " (giờ mặc định — sẽ học từ số liệu khi đủ bài)." : "."}
            <span className="hidden md:inline"> Kéo thẻ bài sang ngày khác để dời.</span>
          </p>
        </>
      ) : null}
      <PostSheet post={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function isToday(day: string) {
  return new Date(`${day}T00:00:00`).toDateString() === new Date().toDateString();
}

function DayBody({ day, onOpen, draggable }: { day: CalendarDay; onOpen: (p: PostCard) => void; draggable?: boolean }) {
  if (day.rest && !day.posts.length) return <p className="self-center text-[13px] text-ink-3">Nghỉ</p>;
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
      {day.posts.map((p) => (
        <button
          key={p.id}
          type="button"
          draggable={draggable && MOVABLE.has(p.status)}
          onDragStart={(e) => e.dataTransfer.setData("application/json", JSON.stringify({ id: p.id, scheduled_at: p.scheduled_at }))}
          onClick={() => onOpen(p)}
          className={cn(
            "flex w-full min-w-0 flex-col gap-1 rounded-md border px-2 py-1.5 text-left text-[13px]",
            tone[p.display_status] ?? tone.pending,
            draggable && MOVABLE.has(p.status) && "cursor-grab active:cursor-grabbing",
          )}
        >
          {/* giờ + kênh một dòng riêng, tên bài chiếm cả bề ngang thẻ (cột ngày hẹp không cắt giờ) */}
          <span className="flex min-w-0 items-center gap-1.5" title={p.channel_label}>
            <ChannelMark channel={p.channel} className="size-5 shrink-0 text-[10px]" />
            {p.display_status === "draft_pushed" ? null : <span className="shrink-0 font-semibold tabular-nums">{formatTime(p.scheduled_at)}</span>}
            {/* cột ngày trên máy tính hẹp: dấu kênh đã đủ nhận ra, tên kênh chỉ hiện khi màn rất rộng */}
            <span className={cn("min-w-0 truncate", draggable && p.display_status !== "draft_pushed" && "sr-only 2xl:not-sr-only")}>{p.channel_label}</span>
          </span>
          <span className="line-clamp-2 min-w-0 text-ink-2">
            {p.display_status === "draft_pushed" ? "Bản nháp chờ chị bấm đăng" : (p.name ?? p.title)}
          </span>
        </button>
      ))}
      {day.suggestions.map((s) => (
        <SuggestionCard key={s.id} s={s} />
      ))}
      {!day.posts.length && !day.suggestions.length ? <p className="text-[13px] text-ink-3">Trống</p> : null}
    </div>
  );
}

function SuggestionCard({ s }: { s: SlotSuggestion }) {
  const { user: session } = useSession();
  const accept = useAcceptSuggestion();
  const dismiss = useDismissSuggestion();
  const owner = session?.role === "owner";
  return (
    <div className="rounded-md border border-dashed border-line-strong p-2 text-[13px]">
      <p className="text-ink-2">
        Trống. <span className="font-medium text-ink">AI gợi ý:</span> {s.idea}
      </p>
      <p className="mt-0.5 line-clamp-3 text-[12px] text-ink-3" title={s.reason ?? undefined}>
        {formatTime(s.slot_at)} {s.channel_label}
        {s.reason ? ` · ${s.reason}` : ""}
      </p>
      {owner ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <Button size="sm" loading={accept.isPending} onClick={() => accept.mutate(s.id, { onSuccess: () => notifySuccess("AI đã soạn bài cho ô này, chờ chị duyệt") })}>
            Soạn bài
          </Button>
          <Button size="sm" variant="ghost" icon={<X className="size-4" aria-hidden />} loading={dismiss.isPending} onClick={() => dismiss.mutate(s.id)}>
            Bỏ
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function PostSheet({ post: current, onClose }: { post: PostCard | null; onClose: () => void }) {
  const { user: session } = useSession();
  const owner = session?.role === "owner";
  const reschedule = useReschedule();
  const act = usePostAction();
  const confirm = useConfirm();
  const [at, setAt] = useState("");
  const [url, setUrl] = useState("");
  // giữ bài cuối cùng để hộp vẫn có nội dung trong lúc đóng
  const [post, setPost] = useState<PostCard | null>(current);
  if (current && current !== post) {
    setPost(current);
    setAt(toLocalInput(current.scheduled_at));
    setUrl("");
  }
  if (!post) return <Sheet open={false} onClose={onClose} title="Bài trên lịch" />;
  const movable = MOVABLE.has(post.status);
  const studio = post.drop_id ? `/desk/noi-dung/dot/${post.drop_id}` : post.product_id ? `/desk/noi-dung/san-pham/${post.product_id}` : "/desk/noi-dung";
  return (
    <Sheet open={!!current} onClose={onClose} title={`${post.channel_label} · ${post.name ?? post.title}`} description={formatDateTime(post.scheduled_at)}>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={post.display_status} />
          {post.orders ? <Badge tone="success">{post.orders} đơn từ bài</Badge> : null}
          <span className="text-[12.5px] text-ink-3">mã bài {post.src_code}</span>
        </div>
        {post.error ? <p className="text-[14px] text-seal">Lỗi lần {post.attempts}: {post.error}</p> : null}
        {post.display_status === "pending" || post.display_status === "needs_fix" ? (
          <ButtonLink href={studio} variant="primary">
            {post.display_status === "needs_fix" ? "Mở xưởng để sửa" : "Mở xưởng để duyệt"}
          </ButtonLink>
        ) : (
          <ButtonLink href={studio} variant="secondary">
            Xem bài trong xưởng
          </ButtonLink>
        )}
        {movable ? (
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              reschedule.mutate(
                { id: post.id, scheduled_at: new Date(at).toISOString() },
                { onSuccess: () => { notifySuccess("Đã đổi giờ đăng"); onClose(); } },
              );
            }}
          >
            <Input label="Đổi giờ đăng" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} wrapperClassName="flex-1" />
            <Button type="submit" variant="secondary" loading={reschedule.isPending}>
              Lưu giờ
            </Button>
          </form>
        ) : null}
        {owner && post.status === "draft_pushed" ? (
          <div className="flex flex-col gap-2 rounded-md bg-review-wash p-3">
            <p className="text-[14px]">Bản nháp đã nằm trong hộp thư TikTok. Chị bấm đăng trong app rồi báo lại ở đây.</p>
            <Input label="Link bài TikTok (không bắt buộc)" placeholder="https://www.tiktok.com/…" value={url} onChange={(e) => setUrl(e.target.value)} />
            <Button loading={act.isPending} onClick={() => act.mutate({ id: post.id, action: "mark-published", url }, { onSuccess: () => { notifySuccess("Đã ghi nhận bài TikTok"); onClose(); } })}>
              Đã đăng trong app
            </Button>
          </div>
        ) : null}
        {owner && (post.status === "approved" || post.status === "failed") ? (
          <Button
            variant="secondary"
            loading={act.isPending}
            onClick={() => act.mutate({ id: post.id, action: "publish-now" }, { onSuccess: (r) => { notifySuccess(r.status === "published" || r.status === "draft_pushed" ? "Đã đăng" : "Chưa đăng được, hệ thống sẽ thử lại"); onClose(); } })}
          >
            {post.status === "failed" ? "Thử đăng lại ngay" : "Đăng ngay"}
          </Button>
        ) : null}
        {owner && movable ? (
          <Button
            variant="ghost"
            className="text-seal"
            onClick={async () => {
              if (await confirm({ title: "Huỷ lịch bài này?", message: "Bài không đăng nữa; bản nháp vẫn giữ trong xưởng.", confirmLabel: "Huỷ lịch", tone: "danger" }))
                act.mutate({ id: post.id, action: "cancel" }, { onSuccess: () => { notifySuccess("Đã huỷ lịch"); onClose(); } });
            }}
          >
            Huỷ lịch
          </Button>
        ) : null}
        {post.external_url ? (
          <Link href={post.external_url} target="_blank" className="inline-flex items-center gap-1 text-[14px] text-accent">
            Xem bài đã đăng <ExternalLink className="size-3.5" aria-hidden />
          </Link>
        ) : null}
      </div>
    </Sheet>
  );
}
