"use client";

import { CalendarClock, Check, Circle, CircleAlert, EyeOff, Hourglass, Minus, PenLine, TriangleAlert, type LucideIcon } from "lucide-react";
import type { BadgeTone } from "@/components/ui/badge";
import type { BoardChannel, BoardChannelKey, BoardKpi, BoardStage, BoardState } from "@/lib/api/content";
import { cn } from "@/lib/cn";
import { formatDayMonth, formatNumber, formatTime, formatVndCompact } from "@/lib/format";
import { CHANNEL_LABEL } from "./shared";

/** Thứ tự kênh trên bảng Xưởng: Website (trang chính thức) rồi từng mạng xã hội. */
export const BOARD_CHANNELS: BoardChannelKey[] = ["website", "facebook", "instagram", "threads", "tiktok", "zalo_oa"];

export const BOARD_CHANNEL_LABEL: Record<BoardChannelKey, string> = { website: "Website", ...CHANNEL_LABEL };

/** Bước công việc của một món (tab Xưởng, badge của Hồ sơ nội dung). */
export const STAGE: Record<BoardStage, { label: string; tone: BadgeTone }> = {
  todo: { label: "Cần soạn", tone: "outline" },
  review: { label: "Chờ chị duyệt", tone: "warning" },
  scheduled: { label: "Đã hẹn giờ", tone: "accent" },
  published: { label: "Đã đăng", tone: "success" },
};

const MARK: Record<BoardChannelKey, string> = { website: "W", facebook: "f", instagram: "IG", threads: "@", tiktok: "TT", zalo_oa: "Z" };

const STATE: Record<BoardState, { label: string; icon: LucideIcon; tone: string }> = {
  na: { label: "Không dùng kênh này", icon: Minus, tone: "border-transparent text-ink-3/60" },
  none: { label: "Chưa có bài", icon: Circle, tone: "border-dashed border-line-strong text-ink-3" },
  drafting: { label: "AI đang soạn", icon: PenLine, tone: "border-transparent bg-soft text-ink-2" },
  pending: { label: "Chờ chị duyệt", icon: Hourglass, tone: "border-transparent bg-review-wash text-review" },
  scheduled: { label: "Đã duyệt, hẹn giờ", icon: CalendarClock, tone: "border-transparent bg-accent-wash text-accent" },
  published: { label: "Đã đăng", icon: Check, tone: "border-transparent bg-auto-wash text-auto" },
  failed: { label: "Đăng lỗi", icon: TriangleAlert, tone: "border-transparent bg-seal-wash text-seal" },
  removed: { label: "Đã gỡ", icon: EyeOff, tone: "border-transparent bg-soft text-ink-3" },
};

/** Câu trạng thái đầy đủ của một kênh (cho tooltip / trình đọc màn hình). */
export function stateText(c: BoardChannel): string {
  const web = c.channel === "website";
  if (c.needs_fix) return "Chờ chị duyệt · còn mục soát cần sửa";
  if (c.raw === "draft_pushed") return "Nháp đã vào app, chờ chị bấm đăng";
  if (web && c.state === "drafting") return "Trang còn nháp";
  if (web && c.state === "pending") return "Trang chờ chị duyệt";
  if (web && c.state === "scheduled") return `Đợt mở lúc ${c.scheduled_at ? `${formatTime(c.scheduled_at)} ${formatDayMonth(c.scheduled_at)}` : "sắp tới"}`;
  if (web && c.state === "removed") return c.raw === "paused" ? "Trang đang tạm ẩn" : "Trang đã gỡ";
  if (c.raw === "hidden") return "Đã ẩn trên kênh (ngừng bán)";
  if (c.state === "scheduled") return c.scheduled_at ? `Đã duyệt, hẹn ${formatTime(c.scheduled_at)} ${formatDayMonth(c.scheduled_at)}` : "Đã duyệt, chưa xếp giờ";
  if (c.state === "published" && c.published_at) return `Đã đăng ${formatDayMonth(c.published_at)}`;
  if (c.state === "failed" && c.error) return `Đăng lỗi: ${c.error}`;
  return STATE[c.state].label;
}

/**
 * Ô trạng thái một kênh: dấu kênh + icon trạng thái (màu theo trạng thái), hẹn giờ thì kèm giờ.
 * Không cần chú giải: rê chuột (title) hoặc trình đọc màn hình đọc đủ câu «Facebook: Đã duyệt, hẹn 20:00 25/11».
 */
export function ChannelState({ cell, className }: { cell: BoardChannel; className?: string }) {
  const s = STATE[cell.needs_fix ? "failed" : cell.state];
  const Icon = cell.needs_fix ? CircleAlert : s.icon;
  const text = `${BOARD_CHANNEL_LABEL[cell.channel]}: ${stateText(cell)}`;
  return (
    <span title={text} className={cn("inline-flex h-7 shrink-0 items-center gap-0.5 rounded-sm border px-1 text-[12px] font-semibold md:gap-1 md:px-1.5", s.tone, className)}>
      <span aria-hidden className="font-display">
        {MARK[cell.channel]}
      </span>
      <Icon aria-hidden className="size-3 md:size-3.5" />
      {cell.state === "scheduled" && cell.scheduled_at ? (
        <span aria-hidden className="font-normal tabular-nums">
          {formatTime(cell.scheduled_at)}
        </span>
      ) : null}
      <span className="sr-only">{text}</span>
    </span>
  );
}

/** Dải trạng thái các kênh của một món. */
export function ChannelStrip({ cells, only }: { cells: BoardChannel[]; only?: BoardChannelKey | null }) {
  return (
    <ul aria-label="Trạng thái từng kênh" className="flex min-w-0 flex-wrap items-center gap-1">
      {cells
        .filter((c) => !only || c.channel === only)
        .map((c) => (
          <li key={c.channel}>
            <ChannelState cell={c} />
          </li>
        ))}
    </ul>
  );
}

const compact = (n: number) => (n >= 10_000 ? `${formatNumber(Math.round(n / 1000))}k` : formatNumber(n));

/** Số liệu bài đã đăng: tiếp cận · tương tác · nhấp link · đơn (doanh thu). Chưa đăng thì nói thẳng. */
export function KpiLine({ kpi, className }: { kpi: BoardKpi | null | undefined; className?: string }) {
  if (!kpi || !kpi.posts) return <p className={cn("text-[13px] text-ink-3", className)}>Chưa có bài đăng</p>;
  const parts: [string, string][] = [
    [compact(kpi.reach), "tiếp cận"],
    [compact(kpi.interactions), "tương tác"],
    [compact(kpi.clicks), "nhấp"],
  ];
  return (
    <p className={cn("flex min-w-0 flex-wrap items-center gap-x-2 text-[13px] text-ink-2 tabular-nums", className)} aria-label="Số liệu bài">
      {parts.map(([v, l]) => (
        <span key={l} className="whitespace-nowrap">
          <span className="font-semibold text-ink">{v}</span> {l}
        </span>
      ))}
      <span className={cn("whitespace-nowrap", kpi.orders ? "font-semibold text-ink" : "text-ink-3")}>
        {kpi.orders ? `${kpi.orders} đơn · ${formatVndCompact(kpi.revenue_vnd)}` : "0 đơn"}
      </span>
    </p>
  );
}
