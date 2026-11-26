import { expect, test, type Page } from "@playwright/test";

/**
 * Ảnh nhà cung cấp: phía chọn hàng (Bàn chọn, hồ sơ thẩm định, Sản phẩm → Hồ sơ chọn) có thư viện ảnh bấm xem lớn;
 * phía bán, chị tự tích ảnh nhà cung cấp để dùng ở trang website (đánh dấu «Ảnh nhà cung cấp» chỉ ở desk); website
 * không lộ link nhà cung cấp. Dữ liệu mẫu có sẵn 2 ảnh nhà cung cấp (đã lưu về kho) cho mỗi ứng viên.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
const NAME = "Móc dán tường chịu lực (bộ 10)";

type Row = { id: string; name: string; slug: string };
type Product = { id: string; slug: string; candidate_id: string; images: { source: string }[] };

async function login(page: Page) {
  const r = await page.request.post("/api/desk/auth/login", { data: OWNER });
  expect(r.ok()).toBe(true);
}

test("ảnh nhà cung cấp: thư viện ở phía chọn, chị chọn dùng lại ở trang website", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "Một luồng ghi dữ liệu, chạy ở khung máy tính");
  test.setTimeout(120_000);
  await login(page);
  const rows: { items: Row[] } = await (await page.request.get("/api/desk/catalog/products", { params: { size: 100 } })).json();
  const row = rows.items.find((r) => r.name.startsWith("Móc dán tường"));
  expect(row, `dữ liệu mẫu cần món «${NAME}»`).toBeTruthy();
  const product: Product = await (await page.request.get(`/api/desk/catalog/products/${row!.id}`)).json();
  const main = page.getByRole("main");

  // ---- Bàn chọn: thư viện ảnh, bấm xem lớn, chuyển ảnh ---------------------------------------------------------
  await page.goto(`/desk/ban-chon/${product.candidate_id}`);
  const gallery = main.getByRole("region", { name: "Ảnh nhà cung cấp" });
  await expect(gallery.getByRole("heading", { name: /Ảnh nhà cung cấp/ })).toBeVisible();
  // 2 ảnh mẫu đã lưu về kho + ảnh bước thẩm định đọc được từ trang nguồn (driver giả: link ảnh giữ chỗ)
  const thumbs = gallery.getByRole("button", { name: /Xem ảnh \d+ lớn/ });
  await expect(thumbs.first()).toBeVisible();
  const n = await thumbs.count();
  expect(n).toBeGreaterThanOrEqual(2);
  await gallery.getByRole("button", { name: "Xem ảnh 1 lớn" }).click();
  const box = page.getByRole("dialog");
  await expect(box.getByText(`Ảnh 1/${n}`)).toBeVisible();
  await expect(box.getByText("Đã lưu bản sao")).toBeVisible();
  const big = box.locator("img").first();
  await expect(big).toHaveAttribute("src", /^\/api\/files\/private\/sourcing\/candidates\//);
  expect(await big.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
  await box.getByRole("button", { name: "Ảnh sau" }).click();
  await expect(box.getByText(`Ảnh 2/${n}`)).toBeVisible();
  await expect(box.getByRole("link", { name: /Mở ảnh gốc/ })).toHaveAttribute("href", /^https:\/\/example\.com\//);
  await box.getByRole("button", { name: "Đóng" }).click();

  // ---- hồ sơ thẩm định + Sản phẩm → Hồ sơ chọn cũng có thư viện -----------------------------------------------------
  await page.goto(`/desk/san-hang/ung-vien/${product.candidate_id}`);
  await expect(main.getByRole("region", { name: "Ảnh nhà cung cấp" }).getByRole("button", { name: /Xem ảnh/ })).toHaveCount(n);
  await page.goto(`/desk/san-pham/${product.id}?tab=chon`);
  await expect(main.getByRole("region", { name: "Ảnh nhà cung cấp" }).getByRole("button", { name: /Xem ảnh/ })).toHaveCount(n);

  // ---- Hồ sơ bán: chị tích một ảnh nhà cung cấp → thành ảnh sản phẩm, có dấu «Ảnh nhà cung cấp» ------------------
  const before = product.images.length;
  await page.goto(`/desk/noi-dung/san-pham/${product.id}`);
  await main.getByRole("button", { name: "Lấy từ ảnh nhà cung cấp" }).click();
  const picker = page.getByRole("dialog", { name: "Lấy từ ảnh nhà cung cấp" });
  await expect(picker.getByText(/hình mờ \(watermark\)/)).toBeVisible();
  await picker.getByRole("button", { name: "Chọn ảnh này" }).first().click();
  await picker.getByRole("button", { name: "Dùng 1 ảnh" }).click();
  await expect(page.getByText("Đã thêm 1 ảnh nhà cung cấp")).toBeVisible();
  await expect(main.getByText("Ảnh nhà cung cấp", { exact: true }).first()).toBeVisible();
  const after: Product = await (await page.request.get(`/api/desk/catalog/products/${product.id}`)).json();
  expect(after.images).toHaveLength(before + 1);
  expect(after.images.filter((i) => i.source === "supplier")).toHaveLength(1);
  // chọn lại: ảnh đã dùng không chọn được nữa
  await main.getByRole("button", { name: "Lấy từ ảnh nhà cung cấp" }).click();
  await expect(page.getByRole("dialog", { name: "Lấy từ ảnh nhà cung cấp" }).getByRole("button", { name: "Ảnh đã dùng" })).toBeDisabled();
  await page.getByRole("dialog", { name: "Lấy từ ảnh nhà cung cấp" }).getByRole("button", { name: "Đóng" }).first().click();

  // ---- website: không lộ link/tên nhà cung cấp, không có nhãn nội bộ -------------------------------------------------
  const html = await (await page.request.get(`/san-pham/${product.slug}`)).text();
  expect(html).not.toContain("example.com/");
  expect(html).not.toContain("Ảnh nhà cung cấp");
  expect(html).not.toContain("private/sourcing");
});
