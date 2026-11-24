"use client";

import { CalendarDays, ChevronRight, Megaphone, PenLine } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge, ButtonLink, Chip, ChipRow, EmptyState, ImageBox, PageHeader, SectionLabel, SkeletonList } from "@/components/ui";
import { useCalendar, useStudio, type StudioItem } from "@/lib/api/content";
import { formatTime } from "@/lib/format";
import { ContentNav, localFile, StatusBadge } from "./shared";

type Filter = "all" | "todo" | "done";

export function ContentHome() {
  const { data, isPending, error } = useStudio();
  const [filter, setFilter] = useState<Filter>("todo");
  const items = useMemo(() => data?.items ?? [], [data]);
  const todo = items.filter((i) => i.pending > 0 || i.drafting > 0 || i.total === 0);
  const done = items.filter((i) => i.total > 0 && i.approved === i.total);
  const shown = filter === "todo" ? todo : filter === "done" ? done : items;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Nội dung"
        description="Một món, mỗi kênh một bản. AI soạn và soát, chị duyệt rồi mới đăng."
        actions={<ButtonLink href="/desk/noi-dung/lich" variant="secondary" size="sm" icon={<CalendarDays className="size-4" aria-hidden />}>Lịch</ButtonLink>}
      />
      <ContentNav />
      <TodayStrip />
      <div className="flex flex-col gap-3">
        <SectionLabel>XƯỞNG NỘI DUNG</SectionLabel>
        <ChipRow>
          <Chip selected={filter === "todo"} count={todo.length} onClick={() => setFilter("todo")}>
            Chờ chị
          </Chip>
          <Chip selected={filter === "done"} count={done.length} onClick={() => setFilter("done")}>
            Đã duyệt hết
          </Chip>
          <Chip selected={filter === "all"} count={items.length} onClick={() => setFilter("all")}>
            Tất cả
          </Chip>
        </ChipRow>
        {isPending ? (
          <SkeletonList rows={4} />
        ) : error ? (
          <EmptyState tone="error" title="Chưa tải được xưởng nội dung" description={error.message} />
        ) : shown.length === 0 ? (
          <EmptyState
            icon={<Megaphone />}
            title={items.length ? "Không còn bài nào chờ chị" : "Chưa có món nào lên web"}
            description={
              items.length
                ? "Mọi bản đã duyệt. Bài mới sẽ hiện ở đây khi có món lên web hoặc đợt mới mở."
                : "Khi một món được đưa lên web, AI tự soạn bài cho Facebook, Instagram, Threads, TikTok và Zalo."
            }
          />
        ) : (
          <ul className="grid gap-2 md:grid-cols-2">
            {shown.map((it) => (
              <li key={`${it.kind}-${it.id}`}>
                <StudioRow item={it} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function StudioRow({ item }: { item: StudioItem }) {
  const href = `/desk/noi-dung/${item.kind === "drop" ? "dot" : "san-pham"}/${item.id}`;
  return (
    <Link
      href={href}
      className="flex items-center gap-3 rounded-md border border-line bg-surface p-3 transition-colors hover:border-line-strong"
    >
      <div className="w-14 shrink-0">
        {item.kind === "drop" ? (
          <div className="grid aspect-square place-items-center rounded-md bg-accent-wash font-display text-[13px] font-bold text-accent">
            ĐỢT
          </div>
        ) : (
          <ImageBox src={localFile(item.image_url)} alt={item.name} ratio="1/1" placeholder="Ảnh" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] font-semibold">{item.name}</p>
        <p className="truncate text-[13px] text-ink-2">{item.subtitle ?? (item.kind === "drop" ? "Đợt mở bán" : "Sản phẩm")}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {item.drafting > 0 ? (
            <Badge tone="accent" icon={<PenLine />}>
              AI đang soạn
            </Badge>
          ) : item.total === 0 ? (
            <Badge tone="outline">Chưa có bài</Badge>
          ) : (
            <Badge tone={item.approved === item.total ? "success" : "neutral"}>
              {item.approved}/{item.total} đã duyệt
            </Badge>
          )}
          {item.needs_fix > 0 ? <Badge tone="danger">{item.needs_fix} cần sửa</Badge> : null}
        </div>
      </div>
      <ChevronRight className="size-5 shrink-0 text-ink-3" aria-hidden />
    </Link>
  );
}

function TodayStrip() {
  const { data } = useCalendar();
  const today = new Date().toDateString();
  const day = data?.days.find((d) => new Date(`${d.day}T00:00:00`).toDateString() === today);
  if (!day || (!day.posts.length && !day.suggestions.length)) return null;
  return (
    <section aria-label="Hôm nay đăng" className="flex flex-col gap-2">
      <SectionLabel aside={<Link href="/desk/noi-dung/lich" className="text-[13px] text-accent">Xem lịch tuần</Link>}>
        HÔM NAY ĐĂNG
      </SectionLabel>
      <ul className="flex flex-col gap-1.5">
        {day.posts.map((p) => (
          <li key={p.id} className="flex flex-wrap items-center gap-2 rounded-md bg-surface px-3 py-2 text-[14px]">
            <span className="font-semibold tabular-nums">{formatTime(p.scheduled_at)}</span>
            <span>{p.channel_label}</span>
            <span className="min-w-0 flex-1 truncate text-ink-2">· {p.name ?? p.title}</span>
            <StatusBadge status={p.display_status} />
          </li>
        ))}
      </ul>
    </section>
  );
}
