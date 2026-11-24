"use client";

import { useEffect, useState } from "react";
import { formatDateTime } from "@/lib/format";

function parts(ms: number) {
  const m = Math.max(0, Math.floor(ms / 60000));
  return { d: Math.floor(m / 1440), h: Math.floor((m % 1440) / 60), m: m % 60 };
}

/** Đếm ngược tới hạn chót đợt: «Còn 2 ngày 14 giờ». Trên máy chủ hiện giờ đóng tuyệt đối. */
export function Countdown({ until, className, prefix = "Còn" }: { until: string; className?: string; prefix?: string }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const t = setInterval(tick, 30_000);
    return () => clearInterval(t);
  }, []);
  const end = new Date(until).getTime();
  let text = `Đóng lúc ${formatDateTime(until)}`;
  if (now !== null) {
    const left = end - now;
    if (left <= 0) text = "Đã hết hạn đặt";
    else {
      const { d, h, m } = parts(left);
      text = d > 0 ? `${prefix} ${d} ngày ${h} giờ` : h > 0 ? `${prefix} ${h} giờ ${m} phút` : `${prefix} ${m} phút`;
    }
  }
  return (
    <time dateTime={new Date(until).toISOString()} className={className} suppressHydrationWarning>
      {text}
    </time>
  );
}
