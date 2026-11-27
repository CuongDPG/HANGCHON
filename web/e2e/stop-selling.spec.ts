import { expect, test, type Page } from "@playwright/test";

/**
 * «Ngừng bán» ở đầu trang sản phẩm: mở màn liệt kê mọi kênh của một món đang bán trong dữ liệu mẫu, bật «Xoá hẳn» thì
 * nút đổi lời, đóng lại không làm gì. Chỉ đọc (không bấm xác nhận) để không đổi dữ liệu mẫu mà bài khác chạy song song
 * đang dùng; luồng ngừng bán / mở bán lại thật nằm ở api/tests/catalog/test_stop_selling.py.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

type Pipeline = { product_id: string; channels_live: string[] };

async function login(page: Page) {
  const r = await page.request.post("/api/desk/auth/login", { data: { email: EMAIL, password: PASSWORD } });
  expect(r.ok()).toBe(true);
}

test("ngừng bán: màn liệt kê mọi kênh của món", async ({ page }) => {
  await login(page);
  const rows: Pipeline[] = await (await page.request.get("/api/desk/catalog/products/pipeline")).json();
  const row = rows.find((r) => r.channels_live.includes("Website") && r.channels_live.length > 1);
  expect(row, "dữ liệu mẫu cần một món đang bán trên website và ít nhất một kênh khác").toBeTruthy();
  const plan = await (await page.request.get(`/api/desk/catalog/products/${row!.product_id}/stop-plan`)).json();

  await page.goto(`/desk/san-pham/${row!.product_id}`);
  const main = page.getByRole("main");
  await main.getByRole("button", { name: "Ngừng bán" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText("Gỡ khỏi kệ website")).toBeVisible();
  for (const p of plan.posts as { label: string }[]) await expect(sheet.getByRole("checkbox", { name: new RegExp(`^${p.label}`) }).first()).toBeVisible();
  const confirm = sheet.getByRole("button", { name: /^Ngừng bán/ });
  await expect(confirm).toBeVisible();
  if (process.env.E2E_SHOTS) await page.screenshot({ path: `test-results/shots/stop-selling-${test.info().project.name}.png`, fullPage: true });
  if ((plan.posts as { can_delete: boolean }[]).some((p) => p.can_delete)) {
    await sheet.getByText("Xoá hẳn bài đã đăng").click();
    await expect(sheet.getByRole("button", { name: "Ngừng bán và xoá hẳn bài" })).toBeVisible();
  }
  await sheet.getByRole("button", { name: "Đóng" }).click();
  await expect(sheet).toBeHidden();
  const after = await (await page.request.get(`/api/desk/catalog/products/${row!.product_id}`)).json();
  expect(after.status).toBe("published");
});
