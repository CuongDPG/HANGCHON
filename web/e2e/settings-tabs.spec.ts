import { expect, test, type Page } from "@playwright/test";

/**
 * Cài đặt dạng tab (theo URL) và tab Mạng xã hội: /desk/cai-dat mở thẳng tab đầu, đi qua các tab, lưu khoá giả cho
 * Trang Facebook ở chế độ giả lập → chỉ hiện 4 ký tự cuối, trang và API không chứa khoá. Không bấm «Kiểm tra kết nối»
 * (sẽ gọi Facebook thật). Đổi xong xoá lại để không ảnh hưởng bài khác.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
const TOKEN = "EAAE2EFAKEPAGETOKEN-khong-that-Q7zP";
const main = (page: Page) => page.getByRole("main");
const tabs = (page: Page) => main(page).getByRole("navigation", { name: "Mục cài đặt" });

test.beforeEach(async ({ page }) => {
  expect((await page.request.post("/api/desk/auth/login", { data: OWNER })).ok()).toBe(true);
});

test("Cài đặt mở tab đầu, đi qua các tab bằng thanh tab", async ({ page }) => {
  await page.goto("/desk/cai-dat");
  await expect(page).toHaveURL(/\/desk\/cai-dat\/cua-hang$/);
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Cửa hàng", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(tabs(page).getByRole("link")).toHaveText(["Cửa hàng", "Mạng xã hội", "Nguồn hàng", "Tích hợp", "AI", "Người phụ giúp", "Tài khoản", "Sao lưu"]);
  await expect(tabs(page).getByRole("link", { name: "Cửa hàng" })).toHaveAttribute("aria-current", "page");

  await expect(page.getByRole("heading", { level: 1, name: "Cài đặt" })).toBeVisible();
  for (const tab of ["Mạng xã hội", "Nguồn hàng", "Tích hợp", "AI", "Tài khoản", "Sao lưu"]) {
    await tabs(page).getByRole("link", { name: tab, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Cài đặt" })).toBeVisible();
    await expect(tabs(page).getByRole("link", { name: tab, exact: true })).toHaveAttribute("aria-current", "page");
  }
  // Tài khoản có chọn sáng/tối (thay nút trên hàng menu)
  await tabs(page).getByRole("link", { name: "Tài khoản" }).click();
  await expect(main(page).getByRole("radiogroup", { name: "Giao diện" })).toBeVisible();
});

test("Mạng xã hội: lưu khoá giả cho Trang Facebook, chỉ hiện 4 ký tự cuối", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "ghi dữ liệu: chỉ chạy một lần (bàn làm việc ưu tiên máy tính)");
  await page.goto("/desk/cai-dat/mang-xa-hoi");
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Mạng xã hội", exact: true })).toHaveAttribute("aria-current", "page");
  for (const name of ["Trang Facebook", "Instagram", "Threads", "TikTok", "Zalo OA", "Nhóm Zalo", "Shopee", "TikTok Shop"]) {
    await expect(main(page).getByRole("region", { name, exact: true })).toBeVisible();
  }
  const fb = main(page).getByRole("region", { name: "Trang Facebook", exact: true });
  await expect(fb.getByText("Giả lập", { exact: true }).first()).toBeVisible();
  await expect(fb.getByText("Chị cần chuẩn bị:")).toBeVisible();
  await expect(fb.getByRole("link", { name: /Meta: Bắt đầu với API Trang/ })).toHaveAttribute("href", /^https:\/\/developers\.facebook\.com\//);

  try {
    await fb.getByLabel("ID Trang", { exact: true }).fill("100000000000001");
    const tokenBox = fb.getByLabel("Mã truy cập Trang (dài hạn)", { exact: true });
    await expect(tokenBox).toHaveAttribute("type", "password");
    await tokenBox.fill(TOKEN);
    await fb.getByRole("button", { name: "Lưu", exact: true }).click();
    await expect(page.getByText("Đã lưu Trang Facebook")).toBeVisible();
    await expect(tokenBox).toHaveValue("");
    await expect(tokenBox).toHaveAttribute("placeholder", /••••Q7zP/);
    await expect(fb.getByText("Giả lập", { exact: true }).first()).toBeVisible(); // lưu khoá không tự bật chạy thật
    expect(await page.content()).not.toContain(TOKEN);
    const api = await page.request.get("/api/desk/control/channels");
    expect(api.status()).toBe(200);
    expect(await api.text()).not.toContain(TOKEN);
    await page.reload();
    await expect(main(page).getByRole("region", { name: "Trang Facebook", exact: true }).getByLabel("ID Trang", { exact: true })).toHaveValue("100000000000001");
  } finally {
    const r = await page.request.patch("/api/desk/control/channels/facebook", { data: { clear: ["page_id", "page_token"] } });
    expect(r.ok()).toBe(true);
  }
});
