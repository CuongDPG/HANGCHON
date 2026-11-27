import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

/**
 * Cài đặt → Nguồn hàng trên API thật có dữ liệu mẫu (scripts/e2e.sh, SOURCES_DRIVER=mock, AI giả).
 * Lưu khoá OneBound giả → chỉ hiện 4 ký tự cuối; chọn «Qua OneBound» cho Taobao và «AI tìm trên web» cho Rakuten qua hộp
 * xác nhận. Không bấm «Kiểm tra kết nối» (sẽ gọi OneBound thật). Đổi xong trả lại như cũ để không ảnh hưởng bài khác.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
const SECRET = "onebound-e2e-khong-that-R4tK";
const main = (page: Page) => page.getByRole("main");
const PLATFORMS = ["1688", "Taobao", "Tmall", "Pinduoduo", "Alibaba.com", "Rakuten", "Amazon Nhật"];

async function ownerLogin(page: Page) {
  expect((await page.request.post("/api/desk/auth/login", { data: OWNER })).ok()).toBe(true);
}

test("chị chọn cách lấy hàng từng sàn và lưu khoá OneBound giả", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "ghi dữ liệu: chỉ chạy một lần (bàn làm việc ưu tiên máy tính)");
  await ownerLogin(page);
  await page.goto("/desk/cai-dat/nguon-hang");
  await expect(page.getByRole("main").getByRole("navigation", { name: "Mục cài đặt" }).getByRole("link", { name: "Nguồn hàng", exact: true })).toHaveAttribute("aria-current", "page");
  for (const name of PLATFORMS) await expect(main(page).getByRole("region", { name, exact: true })).toBeVisible();
  const ob = main(page).getByRole("region", { name: "OneBound (1688, Taobao, Tmall)" });
  const rk = main(page).getByRole("region", { name: "Rakuten Web Service (Rakuten Ichiba)" });
  await expect(ob.getByText("Chị cần chuẩn bị:")).toBeVisible();
  await expect(ob.getByText("Chi phí ước tính:")).toBeVisible();
  await expect(rk.getByRole("link", { name: "Rakuten Developers" })).toHaveAttribute("href", /^https:\/\/webservice\.rakuten\.co\.jp\//);
  await expect(ob.getByText("Chưa thử với khoá thật")).toBeVisible();

  try {
    const taobao = main(page).getByRole("region", { name: "Taobao", exact: true });
    await expect(taobao.getByText("Giả lập", { exact: true }).first()).toBeVisible();
    await taobao.getByRole("radio", { name: "Qua OneBound" }).click();
    const dialog = page.getByRole("alertdialog").or(page.getByRole("dialog"));
    await expect(dialog.getByText(/chưa có khoá/)).toBeVisible();
    await dialog.getByRole("button", { name: "Chạy thật" }).click();
    await expect(taobao.getByText("Chưa nối", { exact: true })).toBeVisible();

    await ob.getByLabel("API key", { exact: true }).fill("onebound-key-e2e-0000");
    const secretBox = ob.getByLabel("API secret", { exact: true });
    await expect(secretBox).toHaveAttribute("type", "password");
    await secretBox.fill(SECRET);
    await ob.getByRole("button", { name: "Lưu", exact: true }).click();
    await expect(page.getByText("Đã lưu OneBound (1688, Taobao, Tmall)")).toBeVisible();
    await expect(secretBox).toHaveValue("");
    await expect(secretBox).toHaveAttribute("placeholder", /••••R4tK/);
    await expect(taobao.getByText("Đã nối", { exact: true })).toBeVisible();
    expect(await page.content()).not.toContain(SECRET);
    const api = await page.request.get("/api/desk/control/sources");
    expect(api.status()).toBe(200);
    expect(await api.text()).not.toContain(SECRET);

    const rakuten = main(page).getByRole("region", { name: "Rakuten", exact: true });
    await rakuten.getByRole("radio", { name: "AI tìm trên web" }).click();
    await page.getByRole("alertdialog").or(page.getByRole("dialog")).getByRole("button", { name: "Chạy thật" }).click();
    await expect(rakuten.getByText("Dùng AI tìm trên web", { exact: true })).toBeVisible();
    await expect(rakuten.getByText(/AI đang chạy giả lập/)).toBeVisible();

    if (process.env.E2E_SHOTS) {
      await page.screenshot({ path: path.join("test-results", "shots", "nguon-hang", "desktop-filled.png"), fullPage: true });
    }
  } finally {
    for (const p of ["taobao", "rakuten"]) {
      expect((await page.request.patch(`/api/desk/control/sources/platforms/${p}`, { data: { driver: null } })).ok()).toBe(true);
    }
    expect((await page.request.patch("/api/desk/control/sources/accounts/onebound", { data: { clear: ["api_key", "api_secret"] } })).ok()).toBe(true);
  }
});

test("người phụ giúp không thấy tab Nguồn hàng", async ({ page, browser }, info) => {
  const email = `phu-nguon-${info.project.name}-${Date.now()}@hangchon.local`;
  const password = "matkhau-phu-e2e-123";
  await ownerLogin(page);
  expect((await page.request.post("/api/desk/users", { data: { email, name: "Phụ e2e", password, role: "helper" } })).status()).toBe(201);
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const helper = await ctx.newPage();
  expect((await helper.request.post("/api/desk/auth/login", { data: { email, password } })).ok()).toBe(true);
  await helper.goto("/desk/cai-dat/cua-hang");
  const tabs = main(helper).getByRole("navigation", { name: "Mục cài đặt" });
  await expect(tabs.getByRole("link", { name: "Tích hợp" })).toBeVisible();
  await expect(tabs.getByRole("link", { name: "Nguồn hàng" })).toHaveCount(0);
  await helper.goto("/desk/cai-dat/nguon-hang");
  await expect(main(helper).getByText("Chỉ chị (chủ cửa hàng) xem được phần này")).toBeVisible();
  expect((await helper.request.get("/api/desk/control/sources")).status()).toBe(403);
  expect((await helper.request.patch("/api/desk/control/sources/profiles/amazon_jp", { data: { fields: { max_images: 3 } } })).status()).toBe(403);
  expect((await helper.request.post("/api/desk/control/sources/profiles/try", { data: { url: "https://www.amazon.co.jp/dp/B08B69661S" } })).status()).toBe(403);
  await ctx.close();
});

test("cấu hình nâng cao: thử với một link, sửa một ô rồi khôi phục mặc định", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "ghi dữ liệu: chỉ chạy một lần");
  await ownerLogin(page);
  await page.goto("/desk/cai-dat/nguon-hang");
  const amazon = main(page).getByRole("region", { name: "Amazon Nhật", exact: true });
  await amazon.getByText("Cấu hình nâng cao").click();
  await expect(amazon.getByLabel("Link chuẩn", { exact: true })).toHaveValue("https://www.amazon.co.jp/dp/{id}");
  await expect(amazon.getByText("(đang dùng mặc định)")).toBeVisible();

  const tryBox = amazon.getByRole("region", { name: "Thử với một link" });
  await tryBox.getByLabel("Link sản phẩm").fill("https://www.amazon.co.jp/%E3%83%98%E3%82%A2%E3%82%B4%E3%83%A0/dp/B08B69661S/ref=sr_1_1?qid=1");
  await tryBox.getByLabel("Link ảnh (không bắt buộc)").fill("https://m.media-amazon.com/images/I/61SrKBHi8ML._AC_SX300_.jpg");
  await tryBox.getByRole("button", { name: "Thử" }).click();
  const out = tryBox.getByLabel("Kết quả thử");
  await expect(out.getByText("B08B69661S", { exact: true })).toBeVisible();
  await expect(out.getByText("https://www.amazon.co.jp/dp/B08B69661S", { exact: true })).toBeVisible();
  await expect(out.getByText("https://m.media-amazon.com/images/I/61SrKBHi8ML.jpg", { exact: true })).toBeVisible();
  await expect(out.getByText("hợp lệ", { exact: true })).toBeVisible();

  try {
    // sai thì báo ngay, không lưu
    await amazon.getByLabel("Link chuẩn", { exact: true }).fill("https://www.amazon.co.jp/dp/");
    await amazon.getByRole("button", { name: "Lưu cấu hình" }).click();
    await expect(page.getByText(/phải bắt đầu bằng https:\/\/ và có \{id\}/)).toBeVisible(); // chỉ một: toast, không có lỗi chưa bắt (overlay)
    await amazon.getByLabel("Link chuẩn", { exact: true }).fill("https://www.amazon.co.jp/dp/{id}");

    await amazon.getByLabel("Số ảnh tối đa", { exact: true }).fill("6");
    await amazon.getByRole("button", { name: "Lưu cấu hình" }).click();
    await expect(page.getByText("Đã lưu cấu hình nâng cao Amazon Nhật")).toBeVisible();
    await expect(amazon.getByText("Đã sửa 1 ô")).toBeVisible();
    if (process.env.E2E_SHOTS) {
      await amazon.screenshot({ path: path.join("test-results", "shots", "nguon-hang", "advanced-amazon.png") });
    }
    await amazon.getByRole("button", { name: "Khôi phục mặc định" }).click();
    await page.getByRole("alertdialog").or(page.getByRole("dialog")).getByRole("button", { name: "Khôi phục" }).click();
    await expect(amazon.getByText("(đang dùng mặc định)")).toBeVisible();
    await expect(amazon.getByLabel("Số ảnh tối đa", { exact: true })).toHaveValue("12");
  } finally {
    expect((await page.request.delete("/api/desk/control/sources/profiles/amazon_jp")).status()).toBe(204);
  }
});

test("màn Nguồn hàng gọn ở 390px và 1280px", async ({ page }, info) => {
  await ownerLogin(page);
  await page.goto("/desk/cai-dat/nguon-hang");
  await expect(main(page).getByRole("region", { name: "Taobao", exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  if (process.env.E2E_SHOTS) {
    await page.screenshot({ path: path.join("test-results", "shots", "nguon-hang", `${info.project.name}.png`), fullPage: true });
  }
});
