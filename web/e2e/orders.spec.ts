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
  const product = catalog.find((p) => p.drops.some((d) => d.status === "open"));
  test.skip(!product, "Cần một món đang bán theo đợt (chạy seed)");
  // đợt riêng của bài này: lấy «đợt đang mở đầu tiên» có thể trúng đợt của bài vòng đời chạy song song (món mới, tên
  // đứng đầu danh sách) — bài đó chốt đợt và cho lô về ngay → đơn của bài này thành «Chờ giao» trước khi kịp kiểm
  const created = await page.request.post("/api/desk/catalog/drops", {
    data: {
      title: `Đợt thử đặt hàng ${info.project.name} ${Date.now() % 100000}`,
      closes_at: new Date(Date.now() + 3 * 86400_000).toISOString(),
      expected_arrival_date: new Date(Date.now() + 20 * 86400_000).toISOString().slice(0, 10),
      items: [{ product_id: product!.product_id, slots_total: 5, max_per_order: 3 }],
    },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const { id: dropId } = (await created.json()) as { id: string };
  const opened = await page.request.post(`/api/desk/catalog/drops/${dropId}/open`);
  expect(opened.ok(), await opened.text()).toBe(true);
  const { code: dropCode, status } = (await opened.json()) as { code: string; status: string };
  expect(status).toBe("open");
  const drop = { drop_id: dropId, code: dropCode, price_vnd: product!.price_vnd };
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
  await page.goto("/gio-hang"); // link cũ chuyển hẳn về «Của tôi», tab Giỏ hàng
  await expect(page).toHaveURL(/\/cua-toi$/);
  await expect(page.getByRole("heading", { level: 1, name: "Của tôi" })).toBeVisible();
  await expect(page.getByRole("main").getByRole("tab", { name: /Giỏ hàng/, selected: true })).toBeVisible();
  await expect(page.getByRole("main").getByText(product!.name)).toBeVisible();
  await expect(page.getByRole("link", { name: /^Của tôi, giỏ hàng 1 món$/ }).filter({ visible: true }).first()).toBeVisible();
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
  await page.goto("/don"); // link cũ chuyển hẳn về «Của tôi», tab Đơn của tôi
  await expect(page).toHaveURL(/\/cua-toi\?tab=don$/);
  await expect(page.getByRole("heading", { level: 1, name: "Của tôi" })).toBeVisible();
  await page.getByRole("main").getByLabel("Số điện thoại", { exact: true }).fill("0900000999");
  await page.getByRole("main").getByLabel("Mã đơn", { exact: true }).fill("HC-11111");
  await page.getByRole("main").getByRole("button", { name: "Xem đơn" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /Không thấy đơn|Không kết nối/ })).toBeVisible();
  await shot(page, "don-tra-cuu", info.project.name);
  await noOverflow(page);
});

test("«Của tôi»: đăng nhập bằng mã một lần, thấy đơn của mình, đăng xuất", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "luồng ghi dữ liệu chỉ chạy một lần");
  test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
  const list = await (await page.request.get("/api/desk/orders?size=50&nhom=xong")).json();
  const done = list.items?.[0] as { code: string; recipient_phone: string } | undefined;
  test.skip(!done, "Cần một đơn đã giao trong dữ liệu mẫu");
  await page.context().clearCookies();

  await page.goto("/cua-toi?tab=don");
  const main = page.getByRole("main");
  await main.getByLabel("Số điện thoại hoặc email").fill(done!.recipient_phone);
  await main.getByRole("button", { name: "Gửi mã" }).click();
  await expect(main.getByRole("status")).toContainText("mình vừa gửi mã 6 chữ số");
  // bản chạy thử (dev/test) hiện mã ngay dưới câu báo
  const devCode = (await main.getByText(/mã là \d{6}/).textContent())!.match(/\d{6}/)![0];
  await main.getByLabel("Mã 6 chữ số").fill(devCode);
  await main.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(main.getByText("Đang đăng nhập:")).toBeVisible();
  const row = main.getByRole("link", { name: new RegExp(done!.code) });
  await expect(row).toBeVisible();
  await shot(page, "cua-toi-don", info.project.name);
  await noOverflow(page);
  await row.click();
  await expect(page).toHaveURL(new RegExp(`/don/${done!.code}\\?t=`));

  await page.goto("/cua-toi?tab=don");
  await main.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(main.getByRole("heading", { name: "Đăng nhập để xem mọi đơn" })).toBeVisible();
});

for (const p of [
  { path: "/desk/don-hang", name: "desk-don-hang", heading: "Đơn" },
  { path: "/desk/don-hang?nhom=cho_giao", name: "desk-cho-giao", heading: "Đơn" },
  { path: "/desk/don-hang/tao", name: "desk-tao-don", heading: "Tạo đơn" },
  { path: "/desk/don-hang/van-hanh", name: "desk-van-hanh-tien", heading: "Tiền về" },
  { path: "/desk/don-hang/van-hanh?tab=ton", name: "desk-van-hanh-ton", heading: "Tồn kho" },
  { path: "/desk/don-hang/van-hanh?tab=san", name: "desk-van-hanh-san", heading: "Sàn" },
  { path: "/desk/don-hang/van-hanh?tab=mau-tin", name: "desk-van-hanh-mau-tin", heading: "Mẫu tin" },
]) {
  test(`mở ${p.path}`, async ({ page }, info) => {
    test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(p.path);
    await expect(page.getByRole("heading", { level: 1, name: p.heading, exact: true })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shot(page, p.name, info.project.name);
    await noOverflow(page);
    expect(errors).toEqual([]);
  });
}

test("chị tạo vận đơn từ mục Chờ giao rồi in nhãn A6", async ({ page }, info) => {
  test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
  // mỗi khổ màn hình một đơn giữ sẵn của dữ liệu mẫu (theo tên người nhận). Không lấy theo vị trí: đơn của bài vòng đời
  // chạy song song cũng vào «Chờ giao» và đứng đầu danh sách (mới nhất) → bài này sẽ tạo mất vận đơn của nó.
  const list = (await (await page.request.get("/api/desk/orders?nhom=cho_giao&size=50")).json()) as { items: { code: string; recipient_name: string }[] };
  const who = info.project.name === "mobile" ? "Phạm Ngọc Lan" : "Trần Thu Hương";
  const target = list.items.find((o) => o.recipient_name === who);
  test.skip(!target, `Không còn đơn chờ giao của ${who} (chạy lại seed)`);
  await page.goto("/desk/don-hang?nhom=cho_giao");
  const main = page.getByRole("main");
  await main.getByRole("checkbox", { name: `Chọn đơn ${target!.code}` }).check();
  await main.getByRole("button", { name: /Tạo vận đơn/ }).click();
  await expect(page).toHaveURL(/\/desk\/don-hang\/in-nhan\?ids=/);
  await expect(page.getByRole("heading", { level: 1, name: "In nhãn" })).toBeVisible();
  await expect(page.locator("article.nhan").first()).toContainText(target!.code);
  await shot(page, "desk-in-nhan", info.project.name);
  await noOverflow(page);
});
