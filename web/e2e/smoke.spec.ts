import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

/**
 * Bài khói: các trang chính mở được ở 390px và 1280px, không lỗi console, không tràn ngang.
 * Chạy được khi API chưa chạy: lỗi tải /api/* (Next.js trả 500 khi không chuyển tiếp được) được bỏ qua,
 * còn trang phải hiện trạng thái trống/lỗi tử tế.
 * Đặt E2E_SHOTS=1 để chụp ảnh toàn trang vào test-results/shots/.
 */

function collectErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const fromApi = /\/api\//.test(msg.location().url) && msg.text().startsWith("Failed to load resource");
    if (!fromApi) errors.push(`console: ${msg.text()}`);
  });
  return errors;
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "trang bị tràn ngang").toBeLessThanOrEqual(0);
}

async function shot(page: Page, name: string, project: string) {
  if (!process.env.E2E_SHOTS) return;
  await page.screenshot({ path: path.join("test-results", "shots", `${name}-${project}.png`), fullPage: true });
}

const PAGES = [
  { path: "/", name: "ke-hang", heading: /Ít nhưng mà chất/ },
  { path: "/desk/dang-nhap", name: "dang-nhap", heading: "Đăng nhập" },
  { path: "/desk/kit", name: "kit", heading: "Bộ giao diện «Chàm»" },
];

for (const p of PAGES) {
  test(`mở ${p.path}`, async ({ page }, info) => {
    const errors = collectErrors(page);
    await page.goto(p.path);
    await expect(page.getByRole("heading", { level: 1, name: p.heading })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expectNoHorizontalOverflow(page);
    await shot(page, p.name, info.project.name);
    expect(errors).toEqual([]);
  });
}

test("kit ở giao diện tối", async ({ page }, info) => {
  const errors = collectErrors(page);
  await page.goto("/desk/kit");
  await page.getByRole("radio", { name: "Tối" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expectNoHorizontalOverflow(page);
  await shot(page, "kit-toi", info.project.name);
  expect(errors).toEqual([]);
});

test("bàn làm việc khi chưa đăng nhập: về trang đăng nhập hoặc báo lỗi kết nối", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/desk/san-hang");
  // API trả 401 → chuyển sang đăng nhập; API chưa chạy → báo chưa kết nối được máy chủ.
  await expect(
    page.getByRole("heading", { level: 1, name: "Đăng nhập" }).or(page.getByRole("heading", { name: "Chưa kết nối được máy chủ" })),
  ).toBeVisible();
  await expectNoHorizontalOverflow(page);
  expect(errors).toEqual([]);
});
