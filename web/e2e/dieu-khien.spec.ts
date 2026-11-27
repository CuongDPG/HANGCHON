import { expect, test, type Page } from "@playwright/test";

/**
 * Lát cắt điều khiển: giao việc bằng lời gọi sang module khác (i6), sao lưu + kiểm khôi phục (k4),
 * thẻ tích hợp thật / giả lập ở Cài đặt. Chạy trên API thật có dữ liệu mẫu (scripts/e2e.sh).
 */
test.skip(!process.env.E2E_API, "cần API thật có dữ liệu mẫu (đặt E2E_API=1)");

async function login(page: Page) {
  await page.goto("/desk/dang-nhap");
  await page.getByLabel("Email").fill(process.env.E2E_EMAIL ?? "chi@hangchon.local");
  await page.getByLabel("Mật khẩu").fill(process.env.E2E_PASSWORD ?? "doimatkhau");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Hôm nay" })).toBeVisible();
}

async function say(page: Page, text: string) {
  const sheet = page.getByRole("dialog");
  await sheet.getByLabel("Lệnh cho AI").fill(text);
  await sheet.getByRole("button", { name: "Gửi cho AI" }).click();
  return sheet.getByRole("status");
}

test("Nói với AI: tóm tắt đơn, tìm khách, chi phí AI; câu không hiểu thì hỏi lại", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Nói với AI" }).click();

  let result = await say(page, "tóm tắt đơn hôm nay");
  await expect(result).toContainText("Đã giao: Tóm tắt đơn hàng");
  await expect(result).toContainText("Đơn mới hôm nay");

  result = await say(page, "tìm khách số 0900 000 103");
  await expect(result).toContainText("Phạm Ngọc Lan");
  await expect(result.getByRole("link", { name: "Mở →" })).toHaveAttribute("href", /\/desk\/khach\/so-khach\//);

  result = await say(page, "tháng này AI tốn bao nhiêu tiền");
  await expect(result).toContainText("AI đã dùng");

  result = await say(page, "thời tiết hôm nay thế nào");
  await expect(result).toContainText("Em cần chị nói rõ hơn");
});

test("Sao lưu: sao lưu ngay, kiểm khôi phục, thấy lần thành công và bản ngoài máy chủ", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "ghi dữ liệu: chỉ chạy một lần (bàn làm việc ưu tiên máy tính)");
  await login(page);
  await page.goto("/desk/cai-dat/sao-luu");
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Sao lưu", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Bản ngoài máy chủ")).toBeVisible();
  await page.getByRole("button", { name: "Sao lưu ngay" }).click();
  await expect(page.getByText(/^Đã sao lưu/)).toBeVisible({ timeout: 30_000 });
  const row = page.getByRole("listitem").filter({ hasText: "Chị bấm sao lưu" }).first();
  await row.getByRole("button", { name: "Kiểm khôi phục" }).click();
  await expect(row.getByText("Đã kiểm: dùng được")).toBeVisible({ timeout: 30_000 });
  await expect(row.getByText(/checksum khớp/)).toBeVisible();
  await expect(page.getByText("Chưa có", { exact: true })).toHaveCount(0); // ô «Lần thành công gần nhất» đã có giờ
});

test("Cài đặt: thẻ cho biết tích hợp nào chạy thật, cái nào còn giả lập", async ({ page }) => {
  await login(page);
  await page.goto("/desk/cai-dat");
  await page.getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Tích hợp" }).click();
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Tích hợp", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("main").getByText(/còn giả lập/).first()).toBeVisible();
  await expect(page.getByRole("main").getByText(/Còn giả lập: .*Báo tin cho khách/)).toBeVisible();
  await expect(page.getByText("Tin báo khách ghi là đã gửi nhưng không tới khách.")).toBeVisible();
});
