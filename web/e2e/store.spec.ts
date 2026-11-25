import { expect, test } from "@playwright/test";

/**
 * Luồng chính của khách trên website (lát cắt store): kệ hàng → tìm không dấu → trang sản phẩm (con dấu, lý do chọn)
 * → hồ sơ chọn → hỏi trợ lý → đợt gom → nhờ chị tìm.
 * Cần API đang chạy với dữ liệu mẫu (`uv run python -m app.seed --demo`, scripts/e2e.sh tự dựng); không có thì bỏ qua.
 */
test.describe("website: kệ hàng → sản phẩm → hồ sơ chọn", () => {
  test.beforeEach(async ({ request }) => {
    const res = await request.get("/api/store/catalog/shelf").catch(() => null);
    const ok = res?.ok() ? ((await res.json()) as { total: number }).total > 0 : false;
    test.skip(!ok, "API chưa chạy hoặc chưa có dữ liệu mẫu");
  });

  test("tìm món, xem hồ sơ chọn, hỏi trợ lý", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Món nào cũng đã dùng thử");
    await page.getByRole("searchbox", { name: "Tìm trên kệ" }).fill("binh giu nhiet");
    await page.getByRole("searchbox", { name: "Tìm trên kệ" }).press("Enter");
    await expect(page).toHaveURL(/q=binh/);
    // món cố định của dữ liệu mẫu (bài vòng đời chạy song song có thể đăng thêm một «Bình giữ nhiệt…» khác)
    const card = page.getByRole("main").getByRole("link", { name: /Bình giữ nhiệt nắp bật 500 ml/ }).first();
    await expect(card.getByRole("img", { name: /Đã chọn 1 trong/ })).toBeVisible();
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
    await expect(main.getByText("Đã chuyển cho chị", { exact: true })).toBeVisible();

    await main.getByRole("link", { name: "Xem hồ sơ chọn" }).click();
    await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toContainText("chọn 1");
    await expect(page.getByRole("main").getByText("Mẫu B", { exact: false }).first()).toBeVisible();
  });

  test("đợt gom và nhờ chị tìm", async ({ page }) => {
    await page.goto("/dot");
    await expect(page.getByRole("main").getByText(/Đang mở/).first()).toBeVisible();
    await expect(page.getByRole("main").getByText(/^Còn \d+ (ngày|giờ|phút)/).first()).toBeVisible();

    await page.goto("/nho-tim");
    const main = page.getByRole("main");
    await main.getByRole("textbox", { name: "Món bạn cần tìm" }).fill(`Móc treo khăn dán tường thử ${Date.now() % 100000}`);
    await main.getByRole("button", { name: "Gửi" }).click();
    await expect(main.getByRole("status")).toContainText("Chị xem qua rồi mới hiện");
  });
});
