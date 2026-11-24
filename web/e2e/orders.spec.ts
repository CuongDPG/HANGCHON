import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

/**
 * Luồng chính của đơn hàng (e4, e5, g1, g2): giỏ → đặt hàng một trang → mã QR → tiền về (giả lập) → trang theo dõi
 * tự cập nhật → chị thấy đơn ở bàn làm việc. Cần API thật đang chạy với dữ liệu mẫu (`app.seed --demo`, scripts/e2e.sh tự dựng)
 * và driver thanh toán giả; không có API thì bỏ qua.
 *   E2E_BASE_URL=http://localhost:3015 E2E_SHOTS=1 bunx playwright test e2e/orders.spec.ts
 */

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };

type Sellable = { product_id: string; name: string; slug: string; price_vnd: number; stock_available: number | null; drops: { drop_id: string; code: string; status: string; price_vnd: number; available: number | null }[] };

async function shot(page: Page, name: string, project: string) {
  if (!process.env.E2E_SHOTS) return;
  await page.screenshot({ path: path.join("test-results", "shots", `${name}-${project}.png`), fullPage: true });
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "trang bị tràn ngang").toBeLessThanOrEqual(0);
}

async function login(page: Page): Promise<boolean> {
  const r = await page.request.post("/api/desk/auth/login", { data: OWNER }).catch(() => null);
  return !!r && r.ok();
}

test("khách đặt hàng trong đợt, chuyển khoản QR, chị thấy đơn đã trả", async ({ page }, info) => {
  test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
  const catalog = (await (await page.request.get("/api/desk/orders/catalog")).json()) as Sellable[];
  const product = catalog.find((p) => p.drops.some((d) => d.status === "open" && (d.available ?? 99) > 0));
  test.skip(!product, "Cần một đợt đang mở (chạy seed)");
  const drop = product!.drops.find((d) => d.status === "open")!;
  await page.context().clearCookies(); // khách không đăng nhập

  await page.goto("/");
  await page.evaluate(
    ([p, d]) =>
      localStorage.setItem(
        "hc_cart_v1",
        JSON.stringify([{ key: `${p.product_id}:${d.drop_id}:`, productId: p.product_id, slug: p.slug, name: p.name, priceVnd: d.price_vnd, dropId: d.drop_id, dropLabel: `Đợt ${d.code}`, quantity: 1 }]),
      ),
    [product!, drop] as const,
  );
  await page.goto("/gio-hang");
  await expect(page.getByRole("heading", { level: 1, name: "Giỏ hàng" })).toBeVisible();
  await expect(page.getByRole("main").getByText(product!.name)).toBeVisible();
  await expect(page.getByRole("link", { name: /Giỏ hàng, 1 món/ })).toBeVisible();
  await shot(page, "gio-hang", info.project.name);
  await noOverflow(page);

  await page.getByRole("main").getByRole("link", { name: "Đặt hàng" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Đặt hàng" })).toBeVisible();
  const main = page.getByRole("main");
  await main.getByLabel("Số điện thoại").fill("090 000 0199");
  await main.getByLabel("Họ tên").fill("Khách Thử Nghiệm");
  await main.getByLabel("Địa chỉ nhận hàng").fill("12 Ngõ Mẫu");
  await main.getByLabel("Tỉnh/thành").fill("Hà Nội");
  await expect(main.getByText("Phí giao", { exact: true }).filter({ visible: true })).toBeVisible();
  await expect(main.getByText(/hàng về dự kiến/).filter({ visible: true })).toBeVisible();
  await shot(page, "dat-hang", info.project.name);
  await noOverflow(page);
  await main.getByRole("button", { name: "Đặt hàng" }).filter({ visible: true }).click();

  await expect(page).toHaveURL(/\/don\/HC-\d{5}\?t=/);
  await expect(page.getByRole("heading", { level: 1, name: /Đơn HC-\d{5}/ })).toBeVisible();
  const qr = page.getByAltText("Mã VietQR chuyển khoản");
  await expect(qr).toBeVisible();
  await expect.poll(() => qr.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
  const code = decodeURIComponent(new URL(page.url()).pathname.split("/").pop()!);
  const content = await page.getByText(/^HC \d{5}$/).first().textContent();
  await shot(page, "don-cho-chuyen-khoan", info.project.name);
  await noOverflow(page);

  // giả lập tiền về (driver thanh toán giả) — trang tự cập nhật
  expect(await login(page)).toBe(true);
  const due = Number((await page.getByText("Số tiền").locator("..").textContent())!.replace(/\D/g, ""));
  const sim = await page.request.post("/api/desk/orders/payments/simulate", { data: { amount_vnd: due, content: `${content} chuyen tien` } });
  expect(sim.ok()).toBe(true);
  await expect(page.getByText("Đã nhận đơn, đã thanh toán")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByAltText("Mã VietQR chuyển khoản")).toHaveCount(0);
  await shot(page, "don-da-tra", info.project.name);

  await page.goto(`/desk/don-hang?q=${encodeURIComponent(code)}`);
  const row = page.getByRole("main").getByRole("link", { name: new RegExp(code) });
  await expect(row).toBeVisible();
  await expect(row.getByText("Chờ hàng về")).toBeVisible();
  await row.click();
  await expect(page.getByRole("heading", { level: 1, name: code })).toBeVisible();
  await shot(page, "desk-chi-tiet-don", info.project.name);
  await noOverflow(page);
});

test("tra cứu đơn bằng số điện thoại + mã đơn", async ({ page }, info) => {
  await page.goto("/don");
  await expect(page.getByRole("heading", { level: 1, name: "Tra cứu đơn" })).toBeVisible();
  await page.getByRole("main").getByLabel("Số điện thoại").fill("0900000999");
  await page.getByRole("main").getByLabel("Mã đơn").fill("HC-11111");
  await page.getByRole("main").getByRole("button", { name: "Xem đơn" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Không thấy đơn|Không kết nối/ })).toBeVisible();
  await shot(page, "don-tra-cuu", info.project.name);
  await noOverflow(page);
});

for (const p of [
  { path: "/desk/don-hang", name: "desk-don-hang", heading: "Đơn hàng" },
  { path: "/desk/don-hang?nhom=cho_giao", name: "desk-cho-giao", heading: "Đơn hàng" },
  { path: "/desk/don-hang/tao", name: "desk-tao-don", heading: "Tạo đơn" },
  { path: "/desk/don-hang/van-hanh", name: "desk-van-hanh-tien", heading: "Vận hành" },
  { path: "/desk/don-hang/van-hanh?tab=ton", name: "desk-van-hanh-ton", heading: "Vận hành" },
  { path: "/desk/don-hang/van-hanh?tab=san", name: "desk-van-hanh-san", heading: "Vận hành" },
  { path: "/desk/don-hang/van-hanh?tab=mau-tin", name: "desk-van-hanh-mau-tin", heading: "Vận hành" },
]) {
  test(`mở ${p.path}`, async ({ page }, info) => {
    test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(p.path);
    await expect(page.getByRole("heading", { level: 1, name: p.heading })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shot(page, p.name, info.project.name);
    await noOverflow(page);
    expect(errors).toEqual([]);
  });
}

test("chị tạo vận đơn từ mục Chờ giao rồi in nhãn A6", async ({ page }, info) => {
  test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
  const list = await (await page.request.get("/api/desk/orders?nhom=cho_giao")).json();
  const target = list.items[info.project.name === "mobile" ? 0 : 1]; // hai cấu hình chạy song song: mỗi bên một đơn
  test.skip(!target, "Không còn đơn chờ giao (chạy lại seed)");
  await page.goto("/desk/don-hang?nhom=cho_giao");
  const main = page.getByRole("main");
  await main.getByRole("checkbox", { name: `Chọn đơn ${target.code}` }).check();
  await main.getByRole("button", { name: /Tạo vận đơn/ }).click();
  await expect(page).toHaveURL(/\/desk\/don-hang\/in-nhan\?ids=/);
  await expect(page.getByRole("heading", { level: 1, name: "In nhãn" })).toBeVisible();
  await expect(page.locator("article.nhan").first()).toContainText(target.code);
  await shot(page, "desk-in-nhan", info.project.name);
  await noOverflow(page);
});
