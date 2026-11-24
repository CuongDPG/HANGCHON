import { expect, test, type Page } from "@playwright/test";

/**
 * Luồng chính Săn hàng + Thẩm định (a1 → a4 → b1/b4): ra đề → AI hiểu là → tìm → mở ứng viên → thẩm định →
 * thấy điểm 7 tiêu chí và ba nút Loại / Mua mẫu / Chọn.
 * Cần API thật đang chạy (AI giả, nguồn giả) và tài khoản chị: E2E_OWNER_EMAIL / E2E_OWNER_PASSWORD
 * (mặc định theo api/.env.example). Không đăng nhập được thì bỏ qua.
 */

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

async function login(page: Page) {
  const r = await page.request.post("/api/desk/auth/login", { data: { email: EMAIL, password: PASSWORD } });
  test.skip(!r.ok(), "API chưa chạy hoặc chưa có tài khoản chị");
}

test("ra đề → tìm → hồ sơ thẩm định", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  await page.goto("/desk/san-hang");
  await expect(page.getByRole("heading", { level: 1, name: "Săn hàng" })).toBeVisible();

  await page.getByLabel("Chị muốn tìm gì?").fill("Tìm giá phơi gấp gọn inox 304 cho ban công nhỏ, dưới 300k, hàng Nhật hoặc Trung Quốc");
  await page.getByRole("button", { name: "AI đọc đề" }).click();

  await expect(page).toHaveURL(/\/desk\/san-hang\/de\//);
  const main = page.getByRole("main");
  await expect(main.getByText("AI hiểu là", { exact: false })).toBeVisible();
  await expect(main.getByRole("button", { name: "về tay ≤ 300k" })).toBeVisible();
  // a1: sửa tiêu chí bằng chip — thêm một từ khoá tiếng Trung riêng để nguồn giả trả món mới cho lần chạy này
  await main.getByRole("button", { name: "về tay ≤ 300k" }).click();
  const zh = page.getByLabel("Từ khoá tiếng Trung");
  await zh.fill(`折叠晾衣架 ${Date.now()}${Math.round(Math.random() * 1e6)}`);
  await page.getByRole("button", { name: "Lưu tiêu chí" }).click();
  await expect(page.getByRole("button", { name: "Lưu tiêu chí" })).toBeHidden();
  await main.getByRole("button", { name: "Đúng rồi, tìm đi" }).click();

  const first = main.locator('a[href^="/desk/san-hang/ung-vien/"]').first();
  await expect(first).toBeVisible({ timeout: 60_000 });
  await expect(first).toContainText("Đáng xem vì");
  await first.click();

  await expect(page).toHaveURL(/\/desk\/san-hang\/ung-vien\//);
  const profile = page.getByRole("main");
  const startBtn = profile.getByRole("button", { name: "Thẩm định món này" });
  await expect(profile.getByText("Điểm theo khung của chị").or(startBtn).first()).toBeVisible({ timeout: 30_000 }); // trang đã tải xong
  if (await startBtn.isVisible()) await startBtn.click();
  await expect(profile.getByText("Điểm theo khung của chị")).toBeVisible({ timeout: 60_000 });
  for (const name of ["Chất lượng", "An toàn", "Biên lợi nhuận", "Khác biệt", "Hàng nhái", "Nguồn", "Vận chuyển"]) {
    await expect(profile.getByText(name, { exact: true }).first()).toBeVisible();
  }
  await expect(profile.getByText(/Giá vốn về tay/)).toBeVisible();
  for (const name of ["Loại", "Mua mẫu", "Chọn"]) await expect(profile.getByRole("button", { name, exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // Loại phải ghi lý do; gọi API Bàn chọn (lát cắt selection) — chưa có thì báo lỗi tử tế
  await profile.getByRole("button", { name: "Loại", exact: true }).click();
  await page.getByRole("button", { name: "Biên thấp" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Loại", exact: true }).click();
  await expect(page.getByText(/Đã loại món này|Bàn chọn chưa sẵn sàng/)).toBeVisible();
});

test("dán link → hồ sơ đã dịch và tự thẩm định", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page);
  await page.goto("/desk/san-hang");
  await page.getByRole("button", { name: "Dán link" }).click();
  await page.getByRole("textbox", { name: "Link" }).fill(`https://item.taobao.com/item.htm?id=${Date.now()}`);
  await page.getByRole("button", { name: "Lấy hồ sơ" }).click();
  await expect(page).toHaveURL(/\/desk\/san-hang\/ung-vien\/.+tham-dinh=1/, { timeout: 60_000 });
  await expect(page.getByRole("main").getByText("Điểm theo khung của chị")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("main").getByText(/AI đã đọc \d+ đánh giá/)).toBeVisible();
});
