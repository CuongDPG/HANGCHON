import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

/**
 * g8 + «AI tự làm = ghi nhật ký»: chị thêm món giữ sẵn với tồn đầu kỳ, điều chỉnh có lý do (thấy trong lịch sử),
 * đặt ngưỡng riêng; khách chuyển khoản → Nhật ký AI có dòng «Khớp …» kèm nút hoàn tác.
 * Cần API thật với dữ liệu mẫu (`app.seed --demo`) và thanh toán giả; không có API thì bỏ qua.
 *   E2E_BASE_URL=http://localhost:3032 E2E_SHOTS=1 bunx playwright test e2e/stock-ai-log.spec.ts
 */

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };

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

test.describe.configure({ mode: "serial" });

test("chị nhập tồn đầu kỳ, điều chỉnh có lý do, đặt ngưỡng riêng", async ({ page }, info) => {
  test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
  const cands = (await (await page.request.get("/api/desk/orders/inventory/candidates")).json()) as { product_id: string; name: string }[];
  // hai khổ màn hình chạy song song: mỗi khổ một món để không giành nhau
  const pick = cands[info.project.name === "mobile" ? 1 : 0];
  test.skip(!pick, "Không còn món chưa có tồn kho (chạy lại seed)");
  const name = pick.name;

  await page.goto("/desk/don-hang/van-hanh?tab=ton");
  await expect(page.getByRole("heading", { level: 1, name: "Tồn kho" })).toBeVisible();
  await page.getByRole("button", { name: "Thêm món giữ sẵn" }).first().click();
  const add = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: "Thêm món giữ sẵn" }) });
  await add.getByRole("combobox", { name: "Món" }).click();
  await page.getByRole("option", { name }).click();
  await add.getByLabel("Tồn đầu kỳ").fill("7");
  await add.getByLabel("Ghi chú").fill("Kiểm kho thử");
  await shot(page, "ton-them", info.project.name);
  await add.getByRole("button", { name: "Thêm vào tồn kho" }).click();
  await expect(add).toBeHidden();

  const row = page.getByRole("listitem").filter({ hasText: name });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Điều chỉnh" }).click();
  const sheet = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: `Điều chỉnh tồn · ${name}` }) });
  await expect(sheet.getByText("Tồn đầu kỳ · Kiểm kho thử")).toBeVisible();
  await sheet.getByLabel("Số lượng (+/−)").fill("-2");
  await sheet.getByRole("combobox", { name: "Loại" }).click();
  await page.getByRole("option", { name: "Hỏng / mất" }).click();
  await sheet.getByLabel("Lý do").fill("Vỡ 2 cái khi kiểm hàng");
  await expect(sheet.getByText("Trong kho: 7 → 5 cái")).toBeVisible();
  await shot(page, "ton-dieu-chinh", info.project.name);
  await sheet.getByRole("button", { name: "Ghi điều chỉnh" }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByText("Đã ghi: trong kho 5 cái")).toBeVisible();

  await row.getByRole("button", { name: "Điều chỉnh" }).click();
  await expect(sheet.getByText("Vỡ 2 cái khi kiểm hàng")).toBeVisible();
  await sheet.getByLabel("Báo khi còn ≤").fill("6");
  await sheet.getByRole("button", { name: "Lưu ngưỡng" }).click();
  await expect(page.getByText("Báo khi còn ≤ 6 cái").first()).toBeVisible();
  await sheet.getByRole("button", { name: "Đóng" }).click().catch(() => page.keyboard.press("Escape"));
  await expect(row.getByText("Sắp hết")).toBeVisible();
  await shot(page, "ton-kho", info.project.name);
  await noOverflow(page);
});

test("tiền về được AI tự khớp và hiện trong Nhật ký AI, hoàn tác được", async ({ page }, info) => {
  test.skip(!(await login(page)), "Cần API đang chạy với tài khoản chị");
  const list = (await (await page.request.get("/api/desk/orders", { params: { nhom: "cho_thanh_toan" } })).json()) as {
    items: { id: string; code: string; total_vnd: number; paid_vnd: number }[];
  };
  test.skip(!list.items.length, "Cần một đơn chờ chuyển khoản (chạy seed)");
  const o = list.items[0];
  const detail = (await (await page.request.get(`/api/desk/orders/${o.id}`)).json()) as { transfer_content: string | null };
  const sim = await page.request.post("/api/desk/orders/payments/simulate", {
    data: { amount_vnd: o.total_vnd - o.paid_vnd, content: detail.transfer_content ?? o.code },
  });
  test.skip(!sim.ok(), "Cần thanh toán giả (mock)");

  await page.goto("/desk/nhat-ky-ai");
  const entry = page.getByRole("listitem").filter({ hasText: `Khớp` }).filter({ hasText: o.code }).first();
  await expect(entry).toBeVisible();
  await expect(entry.getByRole("button", { name: "Hoàn tác" })).toBeVisible();
  await expect(page.getByText(/Báo khách: Đã nhận tiền · đơn/).first()).toBeVisible();
  await shot(page, "nhat-ky-ai", info.project.name);
  await noOverflow(page);
});
