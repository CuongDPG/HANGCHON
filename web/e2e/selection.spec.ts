import { expect, test, type APIRequestContext } from "@playwright/test";

/**
 * Luồng chính bàn chọn (c1–c4) trên dữ liệu mẫu: chuyển một ứng viên sang Đang thử, ghi chú thử hàng,
 * đóng dấu Đã chọn, sửa lời rồi chốt; kanban 5 cột trên máy tính.
 * Cần API chạy với dữ liệu mẫu (`python -m app.seed --demo`, scripts/e2e.sh tự dựng);
 * không đăng nhập được thì bỏ qua. Đặt E2E_OWNER_EMAIL / E2E_OWNER_PASSWORD nếu khác mặc định.
 */

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

async function login(request: APIRequestContext) {
  const r = await request.post("/api/desk/auth/login", { data: { email: EMAIL, password: PASSWORD } }).catch(() => null);
  return !!r && r.ok();
}

type Card = { id: string; title: string };

/**
 * Món riêng của từng bài trong cột «Ứng viên» của dữ liệu mẫu. Không lấy «món đầu cột»: các bài khác chạy song song
 * cũng ghi vào cột này (săn hàng, vòng đời thêm ứng viên mới; Hôm nay duyệt gợi ý mua mẫu «Cốc giữ nhiệt…»).
 */
async function seedCard(request: APIRequestContext, title: string): Promise<Card | undefined> {
  const board = await (await request.get("/api/desk/selection/board")).json();
  return (board.columns.candidate as Card[]).find((c) => c.title === title);
}

// Hai bài đầu ghi dữ liệu trên cột «Ứng viên» → chạy lần lượt, mỗi bài trả món về chỗ cũ khi xong.
test.describe.configure({ mode: "serial" });

test("chọn một món: thử → ghi chú → đóng dấu → chốt lời", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "Một luồng ghi dữ liệu, chạy ở khung điện thoại");
  test.skip(!(await login(page.request)), "API chưa chạy hoặc chưa có dữ liệu mẫu");

  const card = await seedCard(page.request, "Giá phơi giày ban công");
  expect(card, "dữ liệu mẫu có «Giá phơi giày ban công» ở cột Ứng viên").toBeTruthy();
  await page.request.post(`/api/desk/selection/candidates/${card!.id}/stage`, { data: { to: "trial" } });

  try {
    await page.goto("/desk/ban-chon?tab=trial");
    await expect(page.getByRole("heading", { level: 1, name: "Bàn chọn" })).toBeVisible();
    await page.getByRole("main").getByRole("link", { name: new RegExp(card!.title) }).first().click();
    await expect(page.getByRole("heading", { level: 1, name: card!.title })).toBeVisible();

    const cm = 40 + (Date.now() % 50); // mỗi lần chạy một số đo khác để không lẫn ghi chú cũ
    await page.getByLabel("Ghi chú thử hàng").fill(`Lắp nhanh, chắc tay. Rộng ${cm} cm. Hơi nặng khi xách.`);
    await page.getByRole("button", { name: "Lưu ghi chú" }).click();
    const point = page.getByRole("listitem").filter({ hasText: `Rộng ${cm} cm.` }).first();
    await expect(point).toBeVisible();
    await expect(point.getByText("Số đo")).toBeVisible();

    await page.getByRole("button", { name: "Đóng dấu Đã chọn" }).click();
    await expect(page.getByRole("heading", { name: "Vì sao mình chọn", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Sửa lời rồi chốt" }).click();
    const sheet = page.getByRole("dialog", { name: "Sửa lời của chị" });
    await expect(sheet).toBeVisible();
    await sheet.getByLabel("Ý 1").fill("Lắp nhanh, chắc tay.");
    await sheet.getByRole("button", { name: "Chốt lời" }).click();
    await expect(page.getByText("Chị đã chốt lời")).toBeVisible();
  } finally {
    await page.request.post(`/api/desk/selection/candidates/${card!.id}/stage`, { data: { to: "candidate" } });
  }
});

test("loại một món phải ghi lý do", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "Một luồng ghi dữ liệu, chạy ở khung điện thoại");
  test.skip(!(await login(page.request)), "API chưa chạy hoặc chưa có dữ liệu mẫu");
  const card = await seedCard(page.request, "Cây phơi đứng 3 tầng");
  expect(card, "dữ liệu mẫu có «Cây phơi đứng 3 tầng» ở cột Ứng viên").toBeTruthy();
  try {
    await page.goto(`/desk/ban-chon/${card!.id}`);
    await page.getByRole("button", { name: "Loại, ghi lý do" }).click();
    const sheet = page.getByRole("dialog", { name: "Loại món này" });
    await sheet.getByRole("button", { name: "Loại món này" }).click();
    await expect(sheet.getByText("Chị ghi vài chữ vì sao loại nhé.")).toBeVisible();
    const reason = `Rò nước ở nắp sau ${2 + (Date.now() % 7)} ngày, lần thử ${Date.now() % 10000}`;
    await sheet.getByLabel("Vì sao loại?").fill(reason);
    await sheet.getByRole("button", { name: "Loại món này" }).click();
    await expect(page.getByRole("main").getByText(reason, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("main").getByText("Lý do loại", { exact: true })).toBeVisible();
    // dữ liệu mẫu: cùng đề có món đã chọn → link sang hồ sơ chọn của món đó
    await expect(page.getByRole("main").getByText("Cùng đề, chị đã chọn")).toBeVisible();
  } finally {
    await page.request.post(`/api/desk/selection/candidates/${card!.id}/stage`, { data: { to: "candidate" } });
  }
});

test("kanban 5 cột trên máy tính, nguồn cung mở được", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "Kanban chỉ có trên máy tính");
  test.skip(!(await login(page.request)), "API chưa chạy hoặc chưa có dữ liệu mẫu");
  await page.goto("/desk/ban-chon");
  for (const col of ["Ứng viên", "Mua mẫu", "Đang thử", "Đã chọn", "Đã loại"]) {
    await expect(page.getByRole("region", { name: col })).toBeVisible();
  }
  await page.goto("/desk/nguon-cung?tab=ncc");
  await expect(page.getByRole("heading", { level: 1, name: "Nguồn cung" })).toBeVisible();
  await expect(page.getByText("Xưởng inox Phật Sơn (ví dụ)")).toBeVisible();
});
