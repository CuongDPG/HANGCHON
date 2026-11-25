import { expect, test } from "@playwright/test";

/**
 * Luồng chính của khách trên website (lát cắt store): kệ hàng → tìm không dấu → trang sản phẩm (con dấu, lý do chọn)
 * → hỏi trợ lý → mua chung → nhờ tìm. Quá trình chọn (hồ sơ chọn) không ra website, link cũ chuyển về trang sản phẩm.
 * Cần API đang chạy với dữ liệu mẫu (`uv run python -m app.seed --demo`, scripts/e2e.sh tự dựng); không có thì bỏ qua.
 */
test.describe("website: kệ hàng → sản phẩm → hỏi trợ lý", () => {
  test.beforeEach(async ({ request }) => {
    const res = await request.get("/api/store/catalog/shelf").catch(() => null);
    const ok = res?.ok() ? ((await res.json()) as { total: number }).total > 0 : false;
    test.skip(!ok, "API chưa chạy hoặc chưa có dữ liệu mẫu");
  });

  test("tìm món, xem lý do chọn, hỏi trợ lý", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Món nào cũng đã dùng thử");
    // website không hiện số của quá trình chọn: con dấu chỉ còn chữ «ĐÃ CHỌN», không «n/m», không «món đã xem»
    await expect(page.getByRole("main").getByText(/món đã xem|1\/24/)).toHaveCount(0);
    await page.getByRole("searchbox", { name: "Tìm trên kệ" }).fill("binh giu nhiet");
    await page.getByRole("searchbox", { name: "Tìm trên kệ" }).press("Enter");
    await expect(page).toHaveURL(/q=binh/);
    // món cố định của dữ liệu mẫu (bài vòng đời chạy song song có thể đăng thêm một «Bình giữ nhiệt…» khác)
    const card = page.getByRole("main").getByRole("link", { name: /Bình giữ nhiệt nắp bật 500 ml/ }).first();
    await expect(card.getByRole("img", { name: "Đã chọn", exact: true })).toBeVisible();
    await card.click();

    const main = page.getByRole("main");
    await expect(main.getByRole("heading", { level: 1 })).toHaveText(/Bình giữ nhiệt/);
    await expect(main.getByRole("heading", { name: "Vì sao mình chọn" })).toBeVisible();
    await expect(main.getByRole("heading", { name: /Điều mình chưa ưng/ })).toBeVisible();
    const ld = await page.locator('script[type="application/ld+json"]').first().textContent();
    const blocks = [JSON.parse(ld ?? "[]")].flat() as { "@type": string }[];
    expect(blocks.map((b) => b["@type"])).toContain("Product");

    const ask = main.getByRole("textbox", { name: /Câu hỏi về/ });
    await ask.fill("Có bảo hành không?");
    await main.getByRole("button", { name: "Gửi câu hỏi" }).click();
    await expect(main.getByText("Đã ghi lại, mình sẽ trả lời", { exact: true })).toBeVisible();

    // quá trình chọn (dải số sàng lọc, hồ sơ chọn với món đã loại) không ra website — chỉ ở desk
    await expect(main.getByRole("link", { name: "Xem hồ sơ chọn" })).toHaveCount(0);
    await expect(main.getByText("so kỹ", { exact: true })).toHaveCount(0);
    await expect(main.getByRole("img", { name: /Đã chọn \d+ trong/ })).toHaveCount(0);
    expect(ld).not.toContain("Tỉ lệ chọn");
    expect(await page.locator('meta[name="description"]').getAttribute("content")).not.toMatch(/chọn \d+ trong/);
    const productPath = new URL(page.url()).pathname;
    await page.goto(`${productPath}/ho-so-chon`);
    await expect(page).toHaveURL(new RegExp(`${productPath}$`));
  });

  test("về người chọn không hiện số liệu bàn chọn", async ({ page }) => {
    await page.goto("/ve-nguoi-chon");
    const main = page.getByRole("main");
    await expect(main.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(main.getByText(/món đã xem|món được chọn|tỉ lệ chọn|tự cập nhật/)).toHaveCount(0);
  });

  test("mua chung và nhờ tìm", async ({ page }) => {
    await page.goto("/dot");
    await expect(page.getByRole("main").getByRole("heading", { level: 1, name: "Mua chung" })).toBeVisible();
    await expect(page.getByRole("main").getByText("Gom đơn mua chung để có giá tốt nhất")).toBeVisible();
    await expect(page.getByRole("main").getByText(/Đang mở/).first()).toBeVisible();
    await expect(page.getByRole("main").getByText(/^Còn \d+ (ngày|giờ|phút)/).first()).toBeVisible();

    await page.goto("/nho-tim");
    const main = page.getByRole("main");
    await main.getByRole("textbox", { name: "Món bạn cần tìm" }).fill(`Móc treo khăn dán tường thử ${Date.now() % 100000}`);
    await main.getByRole("button", { name: "Gửi" }).click();
    await expect(main.getByRole("status")).toContainText("Mình xem qua rồi mới hiện");
  });
});
