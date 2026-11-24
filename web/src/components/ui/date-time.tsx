"use client";

import { useSyncExternalStore } from "react";
import {
  formatDate,
  formatDateTime,
  formatDayMonth,
  formatRelative,
  formatTime,
  formatWeekday,
  type DateInput,
} from "@/lib/format";

export type DateTimeFormat = "date" | "dayMonth" | "time" | "dateTime" | "weekday" | "relative";

const formatters: Record<Exclude<DateTimeFormat, "relative">, (v: DateInput) => string> = {
  date: formatDate,
  dayMonth: formatDayMonth,
  time: formatTime,
  dateTime: formatDateTime,
  weekday: formatWeekday,
};

/* Đồng hồ dùng chung, nhảy mỗi phút; phía máy chủ trả null để không lệch khi hydrate. */
let now = 0;
const subscribers = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(cb: () => void) {
  subscribers.add(cb);
  if (!timer) {
    now = Date.now();
    timer = setInterval(() => {
      now = Date.now();
      subscribers.forEach((s) => s());
    }, 60_000);
  }
  return () => {
    subscribers.delete(cb);
    if (subscribers.size === 0 && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

/** Thời điểm hiện tại (ms) phía client, cập nhật mỗi phút; `null` khi đang render trên máy chủ. */
export function useNow(): number | null {
  return useSyncExternalStore(
    subscribe,
    () => now || null,
    () => null,
  );
}

type DateTimeProps = {
  value: DateInput;
  format?: DateTimeFormat;
  className?: string;
};

/**
 * Ngày giờ theo giờ Việt Nam, bọc trong <time>. `format="relative"` ("10 phút", "hôm qua") hiện ngày tuyệt đối
 * khi render trên máy chủ rồi chuyển sang tương đối sau khi tải xong.
 */
export function DateTime({ value, format = "date", className }: DateTimeProps) {
  const current = useNow();
  const iso = new Date(value).toISOString();
  const text =
    format === "relative" ? (current ? formatRelative(value, current) : formatDayMonth(value)) : formatters[format](value);
  return (
    <time dateTime={iso} title={formatDateTime(value)} className={className}>
      {text}
    </time>
  );
}
