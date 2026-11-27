import { describe, expect, it } from "vitest";
import { DESK_NAV, DESK_PRIMARY_NAV, findDeskNav } from "./desk-nav";
import { STORE_NAV, isStoreNavActive } from "./store-nav";

describe("bản đồ route bàn làm việc", () => {
  it("có đúng 6 mục điều hướng chính, theo đường đi của món hàng", () => {
    expect(DESK_PRIMARY_NAV.map((i) => i.label)).toEqual(["Hôm nay", "Săn hàng", "Bàn chọn", "Sản phẩm", "Nội dung", "Khách"]);
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

  it("menu: Kệ hàng, Mua chung, Nhờ tìm, Dùng thử, Của tôi; Của tôi sáng ở đặt hàng và theo dõi đơn", () => {
    expect(STORE_NAV.map((i) => i.label)).toEqual(["Kệ hàng", "Mua chung", "Nhờ tìm", "Dùng thử", "Của tôi"]);
    expect(isStoreNavActive("/cua-toi", "/cua-toi")).toBe(true);
    expect(isStoreNavActive("/cua-toi", "/dat-hang")).toBe(true);
    expect(isStoreNavActive("/cua-toi", "/don/HC-12345")).toBe(true);
    expect(isStoreNavActive("/cua-toi", "/dot")).toBe(false);
  });
});
