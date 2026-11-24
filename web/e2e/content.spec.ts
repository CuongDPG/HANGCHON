import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

/**
 * Luồng chính khu Nội dung (f1, f3, f5): đăng nhập → xưởng → mở một món → xem bản Facebook → viết lại «Ngắn hơn»
 * → «Duyệt, xếp lịch» → lịch tuần hiện «Đã duyệt, chờ giờ». Kèm mở các màn hình con.
 *
 * Cần API thật có dữ liệu mẫu (app.seed --demo) → chỉ chạy khi đặt E2E_CONTENT=1, vd:
 *   E2E_CONTENT=1 E2E_BASE_URL=http://localhost:3016 bun run e2e e2e/content.spec.ts
 * E2E_SHOTS=1 để chụp ảnh vào test-results/shots/.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

async function login(page: Page) {
  await page.goto("/desk/dang-nhap?next=/desk/noi-dung");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Nội dung" })).toBeVisible();
}

async function shot(page: Page, name: string, project: string) {
  if (!process.env.E2E_SHOTS) return;
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: path.join("test-results", "shots", `${name}-${project}.png`), fullPage: true });
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "trang bị tràn ngang").toBeLessThanOrEqual(0);
}

test.describe.configure({ mode: "serial" });

test("xưởng: viết lại, duyệt, xếp lịch", async ({ page }, info) => {
  await login(page);
  const main = page.getByRole("main");
  await main.getByRole("button", { name: /Tất cả/ }).click();
  await shot(page, "noi-dung", info.project.name);
  await noOverflow(page);

  await main.getByRole("link", { name: /Móc dán tường/ }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Móc dán tường chịu lực (bộ 10)" })).toBeVisible();
  await main.getByRole("tab", { name: /Instagram/ }).click();
  await expect(main.getByLabel("Thứ tự ảnh")).toBeVisible();
  await shot(page, "xuong-instagram", info.project.name);
  await main.getByRole("tab", { name: /TikTok/ }).click();
  await expect(main.getByLabel("Kịch bản theo cảnh")).toBeVisible();
  await shot(page, "xuong-tiktok", info.project.name);

  await main.getByRole("tab", { name: /Threads/ }).click();
  await main.getByRole("button", { name: "Ngắn hơn" }).click();
  await expect(page.getByText(/Đã viết lại/)).toBeVisible();
  await page.waitForLoadState("networkidle");
  await main.getByRole("button", { name: "Duyệt, xếp lịch" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByLabel("Đăng lúc")).toBeVisible();
  await shot(page, "xuong-duyet", info.project.name);
  await sheet.getByRole("button", { name: "Duyệt, xếp lịch" }).click();
  await expect(main.getByRole("tab", { name: "Threads ✓" })).toBeVisible();
  await noOverflow(page);
});

test("lịch đăng và các mục con", async ({ page }, info) => {
  await login(page);
  const main = page.getByRole("main");
  await main.getByRole("link", { name: "Lịch đăng" }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Lịch đăng" })).toBeVisible();
  await expect(main.getByText(/Đã duyệt, chờ giờ/).first()).toBeVisible();
  await main.getByRole("button", { name: "AI xếp lịch tuần" }).click();
  await shot(page, "lich", info.project.name);
  await noOverflow(page);

  for (const [link, heading, name] of [
    ["Bài ra đơn", "Bài nào ra đơn", "so-lieu"],
    ["Giọng của chị", "Giọng của chị", "giong"],
    ["Video ngắn", "Video ngắn", "video"],
    ["Livestream", "Livestream", "livestream"],
  ] as const) {
    await main.getByRole("navigation", { name: "Mục nội dung" }).getByRole("link", { name: link }).click();
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await shot(page, name, info.project.name);
    await noOverflow(page);
  }
  await main.getByRole("link", { name: /Live tối thứ Năm/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Live tối thứ Năm/ })).toBeVisible();
  await expect(main.getByRole("heading", { name: "CÂU KHÁCH HAY HỎI" })).toBeVisible();
  await shot(page, "livestream-chi-tiet", info.project.name);
  await noOverflow(page);
});
