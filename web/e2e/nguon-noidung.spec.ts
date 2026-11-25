import { expect, test, type Page } from "@playwright/test";

/**
 * Chứng từ nguồn gốc (d4) và chốt chặn chữ «chị» trên trang sản phẩm:
 * đăng nhập → mở đơn đặt lô → tải ảnh nhãn gốc → AI đọc (provider fake) → chị sửa số lô → thấy «Chị đã sửa»;
 * mở trang sản phẩm → gõ câu hỏi có «chị» → thẻ cảnh báo hiện kèm gợi ý → «Sửa theo gợi ý» → hết cảnh báo (không lưu).
 *
 * Cần API thật có dữ liệu mẫu (app.seed --demo), AI fake, JOBS_EAGER hoặc worker đang chạy.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

async function login(page: Page) {
  await page.goto("/desk/dang-nhap?next=/desk/nguon-cung");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await page.waitForURL((u) => u.pathname.startsWith("/desk/nguon-cung"));
}

// ảnh JPEG nhỏ (8×8, xám nhạt) làm ảnh nhãn gốc
const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4pLSwzOko+MzZGNywtQFdBRkxOUlNSMj5aYVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDvqKKKkD//2Q==",
  "base64",
);

test("chứng từ: AI đọc, chị sửa; trang sản phẩm: chặn chữ «chị»", async ({ page }, info) => {
  await login(page);
  const pos = await (await page.request.get("/api/desk/supply/purchase-orders?kind=batch&size=5")).json();
  const po = pos.items[0];
  expect(po, "dữ liệu mẫu cần một đơn đặt lô").toBeTruthy();
  await page.goto(`/desk/nguon-cung/don/${po.id}`);
  const main = page.getByRole("main");

  const filename = `nhan-e2e-${info.project.name}.jpg`;
  await main.getByRole("button", { name: "Tải chứng từ" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.locator('input[type="file"]').setInputFiles({ name: filename, mimeType: "image/jpeg", buffer: JPEG });
  await sheet.getByRole("button", { name: "Lưu chứng từ" }).click();
  const item = main.getByRole("listitem").filter({ hasText: filename });
  await expect(item.getByText("AI đọc")).toBeVisible({ timeout: 15_000 });

  await item.getByRole("button", { name: "Sửa" }).click();
  await page.getByRole("dialog").getByLabel("Số lô").fill("LOT-E2E");
  await page.getByRole("dialog").getByRole("button", { name: "Lưu" }).click();
  await expect(item.getByText("Chị đã sửa")).toBeVisible();
  await expect(item.getByText("LOT-E2E")).toBeVisible();

  // dọn: xoá chứng từ vừa tải (giữ dữ liệu mẫu như cũ)
  const docs = await (await page.request.get(`/api/desk/supply/documents?purchase_order_id=${po.id}`)).json();
  for (const d of docs.filter((x: { filename: string }) => x.filename === filename)) {
    await page.request.delete(`/api/desk/supply/documents/${d.id}`);
  }

  const products = await (await page.request.get("/api/desk/catalog/products?size=1")).json();
  // lời trên trang website sửa ở Nội dung → tab Website
  await page.goto(`/desk/noi-dung/san-pham/${products.items[0].id}`);
  await page.getByLabel("Câu hỏi").first().fill("Chị đã dùng thử bao lâu?");
  const warn = page.getByLabel("Xưng hô với khách");
  await expect(warn.getByText("Mình đã dùng thử bao lâu?")).toBeVisible();
  await warn.getByRole("button", { name: "Sửa theo gợi ý" }).click();
  await expect(page.getByLabel("Câu hỏi").first()).toHaveValue("Mình đã dùng thử bao lâu?");
  await expect(page.getByLabel("Xưng hô với khách")).toHaveCount(0);
});
