import { describe, expect, it } from "vitest";
import { DESK_NAV, DESK_PRIMARY_NAV, findDeskNav } from "./desk-nav";
import { isStoreNavActive } from "./store-nav";

describe("bản đồ route bàn làm việc", () => {
  it("có đúng 5 mục điều hướng chính", () => {
    expect(DESK_PRIMARY_NAV.map((i) => i.label)).toEqual(["Hôm nay", "Săn hàng", "Bàn chọn", "Nội dung", "Khách"]);
  });

  it("khoá và đường dẫn không trùng", () => {
    expect(new Set(DESK_NAV.map((i) => i.key)).size).toBe(DESK_NAV.length);
    expect(new Set(DESK_NAV.map((i) => i.href)).size).toBe(DESK_NAV.length);
  });

  it("khớp tiền tố dài nhất, /desk chỉ khớp đúng", () => {
    expect(findDeskNav("/desk")?.key).toBe("today");
    expect(findDeskNav("/desk/san-hang/abc")?.key).toBe("sourcing");
    expect(findDeskNav("/desk/san-pham")?.key).toBe("products");
    expect(findDeskNav("/desk/khong-co")).toBeUndefined();
  });
});

describe("điều hướng website", () => {
  it("Kệ hàng sáng cả ở trang sản phẩm", () => {
    expect(isStoreNavActive("/", "/")).toBe(true);
    expect(isStoreNavActive("/", "/san-pham/binh")).toBe(true);
    expect(isStoreNavActive("/", "/dot")).toBe(false);
    expect(isStoreNavActive("/dot", "/dot/dot-12")).toBe(true);
  });
});
