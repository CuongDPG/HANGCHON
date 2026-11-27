import { expect, test, type Page } from "@playwright/test";

/**
 * Khung đầu trang thống nhất của bàn làm việc (docs/frontend-guide.md, «Ba tầng điều hướng»):
 * mọi trang desk có đầu trang một hàng cao đúng 44px (máy tính 1440×900 và điện thoại 390×844), và trong một khu,
 * chuyển giữa các mục tầng 1 thì nội dung đầu tiên bắt đầu ở cùng một độ cao — trang không nhảy khi đổi mục.
 * Chỉ đọc, không ghi dữ liệu.
 */

test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };

/** Mỗi khu: các mục tầng 1 (khu chỉ có tiêu đề thì một mục). */
const SECTIONS: Record<string, string[]> = {
  "Hôm nay": ["/desk"],
  "Săn hàng": ["/desk/san-hang"],
  "Bàn chọn": ["/desk/ban-chon"],
  "Sản phẩm": ["/desk/san-pham", "/desk/san-pham/dot", "/desk/san-pham/danh-gia", "/desk/san-pham/nho-tim"],
  "Nội dung": ["/desk/noi-dung", "/desk/noi-dung/lich", "/desk/noi-dung/video", "/desk/noi-dung/livestream", "/desk/noi-dung/so-lieu"],
  Khách: ["/desk/khach", "/desk/khach/so-khach", "/desk/khach/khach-quen", "/desk/khach/dung-thu"],
  "Đơn hàng": [
    "/desk/don-hang",
    "/desk/don-hang/van-hanh?tab=tien",
    "/desk/don-hang/van-hanh?tab=doi-tra",
    "/desk/don-hang/van-hanh?tab=ton",
    "/desk/don-hang/van-hanh?tab=san",
  ],
  "Nguồn cung": ["/desk/nguon-cung?tab=ncc", "/desk/nguon-cung?tab=gia-von", "/desk/nguon-cung", "/desk/nguon-cung?tab=lo-hang", "/desk/nguon-cung?tab=chung-tu"],
  "Chờ duyệt": ["/desk/duyet"],
  "Mức tự chủ": ["/desk/tu-chu", "/desk/tu-chu/chi-phi-ai"],
  "Nhật ký AI": ["/desk/nhat-ky-ai", "/desk/nhat-ky-ai?tab=luu-vet"],
  "Báo cáo": ["/desk/bao-cao"],
  "Sổ sách": ["/desk/so-sach", "/desk/so-sach?tab=chi-phi", "/desk/so-sach?tab=hoa-don"],
  "Cài đặt": ["/desk/cai-dat/cua-hang", "/desk/cai-dat/tich-hop", "/desk/cai-dat/tai-khoan"],
};

/** Đo đầu trang và mép trên của phần tử nội dung đầu tiên sau đầu trang (tính từ đầu tài liệu). */
async function measure(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  const header = page.getByRole("main").locator("[data-page-header]:visible");
  await expect(header, `${url}: thiếu đầu trang`).toHaveCount(1);
  await expect(header.locator("h1"), `${url}: còn đang tải`).not.toHaveText("Đang tải…");
  return header.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const next = el.nextElementSibling?.getBoundingClientRect();
    return { height: Math.round(r.height), top: Math.round(r.top + scrollY), contentTop: next ? Math.round(next.top + scrollY) : null };
  });
}

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "desktop") await page.setViewportSize({ width: 1440, height: 900 });
  expect((await page.request.post("/api/desk/auth/login", { data: OWNER })).ok()).toBe(true);
});

test("đầu trang desk cao 44px; đổi mục tầng 1 trong một khu không làm nội dung nhảy", async ({ page }) => {
  test.setTimeout(240_000);
  for (const [section, urls] of Object.entries(SECTIONS)) {
    const tops = new Set<number>();
    const contentTops = new Set<number>();
    for (const url of urls) {
      const m = await measure(page, url);
      expect(m.height, `${section} · ${url}: đầu trang cao ${m.height}px`).toBe(44);
      tops.add(m.top);
      if (m.contentTop !== null) contentTops.add(m.contentTop);
    }
    expect(tops.size, `${section}: đầu trang lệch giữa các mục (${[...tops].join(", ")})`).toBe(1);
    expect(contentTops.size, `${section}: nội dung đầu tiên lệch giữa các mục (${[...contentTops].join(", ")})`).toBe(1);
  }
});

test("mục tầng 1 là tiêu đề: mục đang mở là h1, mục khác là liên kết", async ({ page }) => {
  await page.goto("/desk/san-pham/dot");
  const nav = page.getByRole("main").getByRole("navigation", { name: "Mục trong khu" });
  await expect(nav.getByRole("heading", { level: 1 })).toHaveText("Đợt bán");
  await expect(nav.getByRole("link")).toHaveText(["Sản phẩm", "Đánh giá", "Nhờ tìm"]);
  await nav.getByRole("link", { name: "Đánh giá" }).click();
  await expect(nav.getByRole("heading", { level: 1 })).toHaveText("Đánh giá");
  // tab tầng 2 giữ trong URL (replace): tải lại vẫn đúng tab
  await page.getByRole("tab", { name: "Đang hiện" }).click();
  await expect(page).toHaveURL(/\/desk\/san-pham\/danh-gia\?tab=published$/);
  await page.reload();
  await expect(page.getByRole("tab", { name: "Đang hiện" })).toHaveAttribute("aria-selected", "true");
});

test("chi tiết đang tải vẫn có đầu trang và cùng mũi tên quay lại", async ({ page }) => {
  // đơn không tồn tại: lỗi — vẫn đầu trang 44px, quay lại đúng mục
  await page.goto("/desk/don-hang/00000000-0000-0000-0000-000000000000");
  const header = page.getByRole("main").locator("[data-page-header]:visible");
  await expect(header).toHaveCount(1);
  await expect(header.getByRole("link", { name: "Quay lại" })).toHaveAttribute("href", "/desk/don-hang");
  expect(Math.round((await header.boundingBox())!.height)).toBe(44);
});
