import { describe, expect, it } from "vitest";
import { BOARD_PAGE, isBoardSort, pageOf, sortFromParam, sortParam } from "./board-paging";

describe("pageOf", () => {
  const cards = Array.from({ length: 75 }, (_, i) => i);

  it("vẽ trang đầu và đếm phần còn lại", () => {
    const p = pageOf(cards, BOARD_PAGE);
    expect(p.visible).toHaveLength(30);
    expect(p.more).toBe(45);
    expect(p.notLoaded).toBe(0);
  });

  it("hết thẻ thì không còn «Xem thêm»", () => {
    expect(pageOf(cards, 90).more).toBe(0);
    expect(pageOf([], BOARD_PAGE)).toEqual({ visible: [], more: 0, notLoaded: 0 });
  });

  it("báo phần máy chủ chưa gửi khi cột vượt trần", () => {
    expect(pageOf(cards, 90, 260).notLoaded).toBe(185);
  });
});

describe("cách xếp bàn chọn", () => {
  it("đọc và ghi tham số ?xep", () => {
    expect(sortFromParam("moi")).toBe("newest");
    expect(sortFromParam("cu")).toBe("oldest");
    expect(sortFromParam(null)).toBeNull();
    expect(sortFromParam("newest")).toBeNull();
    expect(sortParam("manual")).toBeNull();
    for (const s of ["newest", "oldest"] as const) expect(sortFromParam(sortParam(s))).toBe(s);
  });

  it("chỉ nhận ba giá trị hợp lệ từ localStorage", () => {
    expect(isBoardSort("manual")).toBe(true);
    expect(isBoardSort("moi")).toBe(false);
    expect(isBoardSort(null)).toBe(false);
  });
});
