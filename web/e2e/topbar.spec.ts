import { expect, test, type Page } from "@playwright/test";

/**
 * Hàng menu trên cùng của bàn làm việc (máy tính): đi bằng mục chính và bằng «Thêm», mục đang mở được đánh dấu
 * (cả trang con), menu dùng được bằng bàn phím, ở 1024px các mục thừa dồn vào «Thêm» (không xuống dòng, không cuộn ngang).
 * Chỉ đọc dữ liệu. Cần API thật (đăng nhập).
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
const nav = (page: Page) => page.getByRole("banner").getByRole("navigation", { name: "Điều hướng" });
const more = (page: Page) => nav(page).getByRole("button", { name: /^Thêm/ });

test.beforeEach(async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "Hàng menu trên chỉ có trên máy tính");
  expect((await page.request.post("/api/desk/auth/login", { data: OWNER })).ok()).toBe(true);
});

test("đi bằng menu trên và «Thêm», đánh dấu mục đang mở, dùng bàn phím", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/desk");
  await expect(page.getByRole("heading", { level: 1, name: "Hôm nay" })).toBeVisible();
  await expect(nav(page).getByRole("link", { name: "Hôm nay" })).toHaveAttribute("aria-current", "page");

  await nav(page).getByRole("link", { name: "Săn hàng" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Săn hàng" })).toBeVisible();
  await expect(nav(page).getByRole("link", { name: "Săn hàng" })).toHaveAttribute("aria-current", "page");
  await expect(nav(page).getByRole("link", { name: "Hôm nay" })).not.toHaveAttribute("aria-current", "page");

  // trang con đánh dấu mục cha
  await page.goto("/desk/noi-dung/lich");
  await expect(page.getByRole("heading", { level: 1, name: "Lịch đăng" })).toBeVisible();
  await expect(nav(page).getByRole("link", { name: "Nội dung" })).toHaveAttribute("aria-current", "page");

  // «Thêm» bằng chuột
  await more(page).click();
  const menu = page.getByRole("menu", { name: /^Thêm/ });
  await expect(menu).toBeVisible();
  await expect(more(page)).toHaveAttribute("aria-expanded", "true");
  await menu.getByRole("menuitem", { name: "Sổ sách" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Thu chi" })).toBeVisible();
  await expect(menu).toBeHidden();
  await more(page).click();
  await expect(menu.getByRole("menuitem", { name: "Sổ sách" })).toHaveAttribute("aria-current", "page");
  await page.keyboard.press("Escape");
  await expect(menu).toBeHidden();
  await expect(more(page)).toBeFocused();

  // «Thêm» bằng bàn phím: ↓ mở và vào mục đầu, ↓ sang mục sau, Enter đi tới
  await page.keyboard.press("ArrowDown");
  await expect(menu).toBeVisible();
  const items = menu.getByRole("menuitem");
  await expect(items.first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(items.nth(1)).toBeFocused();
  await page.keyboard.press("End");
  await expect(items.last()).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/desk\/so-sach/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("một cụm menu canh phải; Cài đặt chỉ ở menu tài khoản; không còn nút sáng/tối", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/desk");
  await expect(page.getByRole("heading", { level: 1, name: "Hôm nay" })).toBeVisible();
  const banner = page.getByRole("banner");
  await expect(banner.getByRole("button", { name: /^Giao diện/ })).toHaveCount(0);

  // logo trái, mục chính + «Thêm» + ảnh đại diện dồn về phải thành một cụm
  const account = banner.getByRole("button", { name: /^Tài khoản/ });
  const logo = (await banner.getByRole("link", { name: /Hàng Chọn/ }).boundingBox())!;
  const first = (await nav(page).getByRole("link").first().boundingBox())!;
  const moreBox = (await more(page).boundingBox())!;
  const accBox = (await account.boundingBox())!;
  expect(accBox.x - (moreBox.x + moreBox.width)).toBeLessThan(24);
  expect(first.x - (logo.x + logo.width)).toBeGreaterThan(120);

  // «Thêm» không còn Cài đặt
  await more(page).click();
  await expect(page.getByRole("menu", { name: /^Thêm/ }).getByRole("menuitem", { name: "Cài đặt" })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // menu tài khoản: tên/email, Cài đặt, Bộ giao diện, Đăng xuất — Cài đặt mở tab đầu
  await account.click();
  const menu = page.getByRole("menu", { name: /^Tài khoản/ });
  await expect(menu.getByRole("menuitem")).toHaveText(["Cài đặt", "Bộ giao diện", "Đăng xuất"]);
  await menu.getByRole("menuitem", { name: "Cài đặt" }).click();
  await expect(page).toHaveURL(/\/desk\/cai-dat\/cua-hang$/);
  await account.click();
  await expect(menu.getByRole("menuitem", { name: "Cài đặt" })).toHaveAttribute("aria-current", "page");
});

test("1024px: mục thừa dồn vào «Thêm», hàng menu một dòng, không cuộn ngang", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 800 });
  await page.goto("/desk/duyet");
  await expect(page.getByRole("heading", { level: 1, name: "Chờ duyệt" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  // mọi mục hiện thẳng nằm trên cùng một dòng, trong bề rộng màn hình
  const links = nav(page).getByRole("link");
  const n = await links.count();
  expect(n).toBeGreaterThan(3);
  const boxes = await Promise.all(Array.from({ length: n }, (_, i) => links.nth(i).boundingBox()));
  const moreBox = (await more(page).boundingBox())!;
  for (const b of [...boxes, moreBox]) {
    expect(b!.y).toBe(boxes[0]!.y);
    expect(b!.x + b!.width).toBeLessThanOrEqual(1024);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  // «Chờ duyệt» không đủ chỗ → nằm trong «Thêm» và «Thêm» được đánh dấu là mục đang mở
  await expect(nav(page).getByRole("link", { name: /Chờ duyệt/ })).toHaveCount(0);
  await more(page).click();
  await expect(page.getByRole("menu", { name: /^Thêm/ }).getByRole("menuitem", { name: /Chờ duyệt/ })).toHaveAttribute("aria-current", "page");
  // rộng ra thì mục quay lại hàng menu
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 1440, height: 800 });
  await expect(nav(page).getByRole("link", { name: /Chờ duyệt/ })).toHaveAttribute("aria-current", "page");
});
