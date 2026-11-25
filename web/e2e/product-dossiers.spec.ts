import { expect, test, type Page } from "@playwright/test";

/**
 * Trang Sản phẩm theo dõi hai chiều: danh sách hiện tình trạng chọn + đường bán từng món → mở một món →
 * tab «Hồ sơ chọn» (dấu vết từng bước) → tab «Hồ sơ bán» (nội dung → lên kênh → khách, số khớp API) →
 * bấm một kênh mở đúng tab ở xưởng nội dung → tab «Giá và cách bán» vẫn sửa được giá.
 *
 * Cần API thật có dữ liệu mẫu (app.seed --demo), xem scripts/e2e.sh.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

type Pipeline = { product_id: string; content_ready: number; content_total: number; orders: number; channels_live: string[] };

async function login(page: Page) {
  await page.goto("/desk/dang-nhap?next=/desk/san-pham");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mật khẩu").fill(PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await page.waitForURL((u) => u.pathname.startsWith("/desk/san-pham"));
}

test("sản phẩm: danh sách hai chiều, Hồ sơ chọn, Hồ sơ bán, Giá và cách bán", async ({ page }) => {
  await login(page);
  const rows: Pipeline[] = await (await page.request.get("/api/desk/catalog/products/pipeline")).json();
  const row = rows.filter((r) => r.orders > 0).sort((a, b) => b.orders - a.orders)[0];
  expect(row, "dữ liệu mẫu cần một món đã có đơn").toBeTruthy();
  const product = await (await page.request.get(`/api/desk/catalog/products/${row.product_id}`)).json();
  const main = page.getByRole("main");

  // ---- danh sách: mỗi dòng có tình trạng chọn + đường bán ----------------------------------------------------------
  const card = main.getByRole("link").filter({ hasText: product.name }).first();
  await expect(card).toBeVisible();
  await expect(card.getByText(`Nội dung ${row.content_ready}/${row.content_total}`)).toBeVisible();
  await expect(card.getByText(new RegExp(`^${row.orders} đơn`))).toBeVisible();
  await card.click();
  await page.waitForURL(new RegExp(`/desk/san-pham/${row.product_id}`));

  // ---- Hồ sơ chọn (tab mặc định): so với các mẫu khác + dấu vết từng bước ------------------------------------------
  await expect(main.getByRole("tab", { name: "Hồ sơ chọn" })).toHaveAttribute("aria-selected", "true");
  const trail = main.getByRole("region", { name: "Dấu vết từng bước" });
  for (const step of ["Săn hàng", "Thẩm định", "Mua mẫu và dùng thử", "Quyết định chọn", "Giá vốn và giá bán"]) {
    await expect(trail.getByRole("heading", { name: step })).toBeVisible();
  }
  await expect(trail.getByRole("link", { name: "Hồ sơ thẩm định →" })).toHaveAttribute("href", `/desk/san-hang/ung-vien/${product.candidate_id}`);

  // ---- Hồ sơ bán: nội dung → lên kênh → khách, số khớp API --------------------------------------------------------
  await main.getByRole("tab", { name: "Hồ sơ bán" }).click();
  await expect(page).toHaveURL(/\?tab=ban$/);
  const sales = await (await page.request.get(`/api/desk/catalog/products/${row.product_id}/sales`)).json();
  const pipeline = main.getByRole("list", { name: "Đường bán" });
  await expect(pipeline.getByText(`${sales.content.ready}/${sales.content.total}`)).toBeVisible();
  await expect(pipeline.getByText(`${sales.customers.orders.count} đơn`)).toBeVisible();
  const content = main.getByRole("region", { name: "1 · Nội dung" });
  await expect(content.getByRole("link")).toHaveCount(7); // xưởng + Website + 5 mạng xã hội
  await expect(main.getByRole("region", { name: "2 · Lên kênh" }).getByText("Website", { exact: true })).toBeVisible();
  const customers = main.getByRole("region", { name: "3 · Khách hàng" });
  await expect(customers.getByRole("heading", { name: "Đơn hàng" })).toBeVisible();
  await expect(customers.getByRole("link", { name: new RegExp(sales.customers.orders.recent[0].code) })).toBeVisible();
  if (sales.customers.posts.simulated) await expect(customers.getByText("Số liệu giả lập")).toBeVisible();

  // bấm một kênh → xưởng nội dung mở đúng tab kênh đó
  await content.getByRole("link", { name: /^Facebook/ }).click();
  await page.waitForURL(/\/desk\/noi-dung\/san-pham\/.+\?kenh=facebook/);
  await expect(main.getByRole("tab", { name: /^Facebook/ })).toHaveAttribute("aria-selected", "true");

  // ---- Giá và cách bán -------------------------------------------------------------------------------------------
  await page.goto(`/desk/san-pham/${row.product_id}?tab=gia`);
  await expect(main.getByRole("tab", { name: "Giá và cách bán" })).toHaveAttribute("aria-selected", "true");
  await expect(main.getByLabel("Giá bán")).toHaveValue(String(product.price_vnd));
});
