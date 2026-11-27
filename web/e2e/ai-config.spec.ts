import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

/**
 * Cài đặt → «AI và khoá API» trên API thật có dữ liệu mẫu (scripts/e2e.sh tự dựng, AI_PROVIDER=fake).
 * Không gọi dịch vụ AI thật: khoá chỉ được lưu sẵn (không chuyển provider), «Kiểm tra kết nối» chạy với AI giả.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");
test.describe.configure({ mode: "serial" });

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
// khoá giả dạng thật, không phải khoá của ai
const KEY = "sk-ant-e2e-0000000000000000000000000000-WXYZ";
const main = (page: Page) => page.getByRole("main");

async function login(page: Page, email: string, password: string, landing = "Hôm nay") {
  await page.goto("/desk/dang-nhap");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { level: 1, name: landing })).toBeVisible();
}

async function pickProvider(page: Page, name: RegExp) {
  await main(page).getByRole("combobox", { name: "Nhà cung cấp AI" }).click();
  await page.getByRole("option", { name }).click();
}

test("chị nhập khoá, lưu, thấy khoá bị che; kiểm tra kết nối với AI giả; xoá khoá", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "luồng ghi dữ liệu chỉ chạy một lần");
  await login(page, OWNER.email, OWNER.password);

  await page.goto("/desk/cai-dat");
  await main(page).getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "AI", exact: true }).click();
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "AI", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(main(page).getByText("Đang dùng: AI giả")).toBeVisible();

  // nhập khoá Anthropic, chỉ lưu sẵn (không chuyển provider → các bài khác vẫn chạy AI giả)
  await pickProvider(page, /Anthropic/);
  const keyInput = main(page).getByLabel("Khoá API");
  await expect(keyInput).toHaveAttribute("type", "password");
  await keyInput.fill(KEY);
  await main(page).getByRole("button", { name: "claude-sonnet-5-5" }).first().click();
  await main(page).getByLabel(/Chuyển sang dùng Anthropic/).uncheck();
  await main(page).getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu cấu hình Anthropic (Claude)")).toBeVisible();

  // khoá chỉ hiện dạng che, ô khoá trống lại; trang và API không chứa khoá thật
  await expect(main(page).getByText("sk-ant-…WXYZ").first()).toBeVisible();
  await expect(keyInput).toHaveValue("");
  expect(await page.content()).not.toContain(KEY);
  const cfg = await page.request.get("/api/desk/control/ai/config");
  expect(cfg.status()).toBe(200);
  const body = await cfg.text();
  expect(body).not.toContain(KEY);
  expect(JSON.parse(body).provider).toBe("fake");
  await expect(main(page).getByText("Đang dùng: AI giả")).toBeVisible();

  // kiểm tra kết nối bằng AI giả (không gọi ra ngoài)
  await pickProvider(page, /AI giả/);
  await main(page).getByRole("button", { name: "Kiểm tra kết nối" }).click();
  const result = main(page).getByLabel("Kết quả kiểm tra");
  await expect(result.getByText("Việc nhanh")).toBeVisible();
  await expect(result.getByText(/· Được/)).toHaveCount(2);

  // xoá khoá đã lưu (hộp xác nhận của ứng dụng, không phải confirm của trình duyệt)
  await pickProvider(page, /Anthropic/);
  await main(page).getByRole("button", { name: "Xoá khoá" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Xoá khoá" }).click();
  await expect(page.getByText("Đã xoá khoá")).toBeVisible();
  await expect(main(page).getByText("Chưa có khoá.")).toBeVisible();
});

test("người phụ giúp không thấy, không vào được cấu hình AI", async ({ page, browser }, info) => {
  const email = `phu-ai-${info.project.name}-${Date.now()}@hangchon.local`;
  const password = "matkhau-phu-e2e-123";
  const owner = await page.request.post("/api/desk/auth/login", { data: OWNER });
  expect(owner.ok()).toBeTruthy();
  const created = await page.request.post("/api/desk/users", { data: { email, name: "Phụ e2e", password, role: "helper" } });
  expect(created.status()).toBe(201);

  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const helper = await ctx.newPage();
  await login(helper, email, password);
  await helper.goto("/desk/cai-dat");
  await expect(helper.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Cửa hàng", exact: true })).toHaveAttribute("aria-current", "page");
  const tabs = main(helper).getByRole("navigation", { name: "Mục cài đặt" });
  await expect(tabs.getByRole("link", { name: "Tích hợp" })).toBeVisible();
  await expect(tabs.getByRole("link", { name: "AI", exact: true })).toHaveCount(0);
  await expect(tabs.getByRole("link", { name: "Mạng xã hội" })).toHaveCount(0);
  await helper.goto("/desk/cai-dat/ai");
  await expect(main(helper).getByText("Chỉ chị (chủ cửa hàng) xem được phần này")).toBeVisible();
  expect((await helper.request.get("/api/desk/control/ai/config")).status()).toBe(403);
  expect((await helper.request.patch("/api/desk/control/ai/config", { data: { provider: "fake" } })).status()).toBe(403);
  await ctx.close();
});

test("màn cấu hình AI gọn ở 390px và 1280px", async ({ page }, info) => {
  await login(page, OWNER.email, OWNER.password);
  await page.goto("/desk/cai-dat/ai");
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "AI", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(main(page).getByRole("combobox", { name: "Nhà cung cấp AI" })).toBeVisible();
  await pickProvider(page, /Anthropic/);
  await expect(main(page).getByLabel("Khoá API")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  if (process.env.E2E_SHOTS) {
    await page.screenshot({ path: path.join("test-results", "shots", "ai-config", `${info.project.name}.png`), fullPage: true });
  }
});
