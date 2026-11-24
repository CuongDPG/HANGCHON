import { describe, expect, it } from "vitest";
import {
  formatDate,
  formatDateTime,
  formatDayMonth,
  formatNumber,
  formatPercent,
  formatRelative,
  formatTime,
  formatVnd,
  formatVndCompact,
  formatWeekday,
} from "./format";

describe("tiền", () => {
  it("định dạng VND có dấu chấm ngăn nghìn", () => {
    expect(formatVnd(385000)).toBe("385.000đ");
    expect(formatVnd(0)).toBe("0đ");
    expect(formatVnd(1234567)).toBe("1.234.567đ");
    expect(formatVnd(-50000)).toBe("-50.000đ");
    expect(formatVnd(999.6)).toBe("1.000đ");
  });

  it("rút gọn cho ô số liệu", () => {
    expect(formatVndCompact(620000)).toBe("620k");
    expect(formatVndCompact(3400000)).toBe("3,4 tr");
    expect(formatVndCompact(28_400_000)).toBe("28,4 tr");
    expect(formatVndCompact(5_000_000)).toBe("5 tr");
    expect(formatVndCompact(1_250_000_000)).toBe("1,3 tỷ");
    expect(formatVndCompact(900)).toBe("900đ");
    expect(formatVndCompact(-2_300_000)).toBe("-2,3 tr");
  });

  it("số và phần trăm", () => {
    expect(formatNumber(1240)).toBe("1.240");
    expect(formatPercent(0.34)).toBe("34%");
    expect(formatPercent(0.345)).toBe("34,5%");
  });
});

describe("ngày giờ theo Asia/Ho_Chi_Minh", () => {
  // 17:30 UTC ngày 24/11 = 00:30 ngày 25/11 giờ Việt Nam
  const lateUtc = "2026-11-24T17:30:00Z";

  it("đổi múi giờ trước khi lấy ngày", () => {
    expect(formatDate(lateUtc)).toBe("25/11/2026");
    expect(formatDayMonth(lateUtc)).toBe("25/11");
    expect(formatTime(lateUtc)).toBe("00:30");
    expect(formatDateTime(lateUtc)).toBe("00:30 · 25/11/2026");
  });

  it("thứ trong tuần", () => {
    expect(formatWeekday("2026-11-25T03:00:00Z")).toBe("Thứ tư, 25/11");
    expect(formatWeekday("2026-11-29T03:00:00Z")).toBe("Chủ nhật, 29/11");
  });

  it("thời gian tương đối", () => {
    const now = new Date("2026-11-25T10:00:00Z"); // 17:00 giờ VN
    expect(formatRelative("2026-11-25T09:59:40Z", now)).toBe("vừa xong");
    expect(formatRelative("2026-11-25T09:50:00Z", now)).toBe("10 phút");
    expect(formatRelative("2026-11-25T08:00:00Z", now)).toBe("2 giờ");
    expect(formatRelative("2026-11-24T10:00:00Z", now)).toBe("hôm qua");
    expect(formatRelative("2026-11-22T10:00:00Z", now)).toBe("3 ngày");
    expect(formatRelative("2026-11-10T10:00:00Z", now)).toBe("10/11");
    expect(formatRelative("2025-11-10T10:00:00Z", now)).toBe("10/11/2025");
    expect(formatRelative("2026-11-27T12:00:00Z", now)).toBe("còn 2 ngày");
    expect(formatRelative("2026-11-25T13:00:00Z", now)).toBe("còn 3 giờ");
  });

  it("qua nửa đêm giờ VN thì là hôm qua dù chưa đủ 24 giờ", () => {
    const now = new Date("2026-11-24T17:30:00Z"); // 00:30 ngày 25/11 giờ VN
    expect(formatRelative("2026-11-24T15:00:00Z", now)).toBe("hôm qua"); // 22:00 ngày 24/11
  });
});
