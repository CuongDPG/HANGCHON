/**
 * Định dạng hiển thị kiểu Việt Nam. Tiền là số nguyên VND; thời gian lưu UTC, hiển thị Asia/Ho_Chi_Minh.
 * Dùng chung cho Server và Client Component (không phụ thuộc trình duyệt).
 */

export const VN_TZ = "Asia/Ho_Chi_Minh";
const LOCALE = "vi-VN";

const intFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const dec1Fmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });

/** Số nguyên có dấu chấm ngăn nghìn: 1240 → "1.240". */
export function formatNumber(value: number): string {
  return intFmt.format(value);
}

/** Tiền VND: 385000 → "385.000đ"; -50000 → "-50.000đ". */
export function formatVnd(value: number): string {
  const rounded = Math.round(value);
  const sign = rounded < 0 ? "-" : "";
  return `${sign}${intFmt.format(Math.abs(rounded))}đ`;
}

/**
 * Tiền rút gọn cho ô số liệu: 620000 → "620k", 3400000 → "3,4 tr", 1250000000 → "1,3 tỷ".
 * Dưới 1.000 vẫn ghi đủ: 900 → "900đ".
 */
export function formatVndCompact(value: number): string {
  const sign = value < 0 ? "-" : "";
  const v = Math.abs(value);
  if (v >= 1_000_000_000) return `${sign}${dec1Fmt.format(v / 1_000_000_000)} tỷ`;
  if (v >= 1_000_000) return `${sign}${dec1Fmt.format(v / 1_000_000)} tr`;
  if (v >= 1_000) return `${sign}${intFmt.format(Math.round(v / 1_000))}k`;
  return `${sign}${intFmt.format(v)}đ`;
}

/** Phần trăm: 0.34 → "34%"; 0.345 → "34,5%". */
export function formatPercent(ratio: number): string {
  return `${dec1Fmt.format(ratio * 100)}%`;
}

export type DateInput = Date | string | number;

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value);
}

/** Lấy các thành phần ngày giờ theo giờ Việt Nam. */
function vnParts(value: DateInput) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: VN_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    weekday: "short",
    hourCycle: "h23",
  }).formatToParts(toDate(value));
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
    minute: get("minute"),
    weekday: get("weekday"), // Mon, Tue…
  };
}

const WEEKDAYS: Record<string, string> = {
  Mon: "Thứ hai",
  Tue: "Thứ ba",
  Wed: "Thứ tư",
  Thu: "Thứ năm",
  Fri: "Thứ sáu",
  Sat: "Thứ bảy",
  Sun: "Chủ nhật",
};

/** "25/11/2026" */
export function formatDate(value: DateInput): string {
  const p = vnParts(value);
  return `${p.day}/${p.month}/${p.year}`;
}

/** "25/11" */
export function formatDayMonth(value: DateInput): string {
  const p = vnParts(value);
  return `${p.day}/${p.month}`;
}

/** "14:05" */
export function formatTime(value: DateInput): string {
  const p = vnParts(value);
  return `${p.hour}:${p.minute}`;
}

/** "14:05 · 25/11/2026" */
export function formatDateTime(value: DateInput): string {
  return `${formatTime(value)} · ${formatDate(value)}`;
}

/** "Thứ tư, 25/11" */
export function formatWeekday(value: DateInput): string {
  const p = vnParts(value);
  return `${WEEKDAYS[p.weekday] ?? ""}, ${p.day}/${p.month}`;
}

/** Số ngày lịch (theo giờ Việt Nam) giữa hai thời điểm. */
function vnDayIndex(value: DateInput): number {
  const p = vnParts(value);
  return Math.floor(Date.UTC(+p.year, +p.month - 1, +p.day) / 86_400_000);
}

/**
 * Thời gian tương đối, ngắn gọn như trong hộp thư: "vừa xong", "10 phút", "2 giờ", "hôm qua", "3 ngày",
 * quá 7 ngày thì ghi ngày "18/11" (khác năm thì "18/11/2025").
 * Mốc tương lai: "còn 2 ngày", "còn 3 giờ", "còn 5 phút".
 */
export function formatRelative(value: DateInput, now: DateInput = Date.now()): string {
  const d = toDate(value);
  const n = toDate(now);
  const diffMs = n.getTime() - d.getTime();
  const future = diffMs < 0;
  const abs = Math.abs(diffMs);
  const min = Math.floor(abs / 60_000);
  const hour = Math.floor(abs / 3_600_000);
  const dayDiff = Math.abs(vnDayIndex(n) - vnDayIndex(d));

  if (future) {
    if (min < 1) return "sắp tới";
    if (min < 60) return `còn ${min} phút`;
    if (hour < 24) return `còn ${hour} giờ`;
    return `còn ${Math.max(1, Math.floor(abs / 86_400_000))} ngày`;
  }
  if (min < 1) return "vừa xong";
  if (min < 60) return `${min} phút`;
  if (hour < 24 && dayDiff === 0) return `${hour} giờ`;
  if (dayDiff <= 1) return "hôm qua";
  if (dayDiff <= 7) return `${dayDiff} ngày`;
  return vnParts(d).year === vnParts(n).year ? formatDayMonth(d) : formatDate(d);
}
