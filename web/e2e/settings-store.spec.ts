import { expect, test, type Page } from "@playwright/test";

/**
 * Cài đặt → Cửa hàng: sửa rồi bấm «Lưu thay đổi» phải lưu thật và hiện ra website.
 * (Lỗi cũ: tên ô dạng «store.picker_name» bị react-hook-form hiểu là đường dẫn lồng nhau → bấm Lưu báo «Không có gì thay đổi».)
 * Đổi xong trả lại giá trị cũ để không ảnh hưởng bài khác.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");
test.describe.configure({ mode: "serial" });

const main = (page: Page) => page.getByRole("main");

async function login(page: Page) {
  await page.goto("/desk/dang-nhap");
  await page.getByLabel("Email").fill(process.env.E2E_EMAIL ?? "chi@hangchon.local");
  await page.getByLabel("Mật khẩu").fill(process.env.E2E_PASSWORD ?? "doimatkhau");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Hôm nay" })).toBeVisible();
}

async function saveStore(page: Page, values: Record<string, string>) {
  await page.goto("/desk/cai-dat/cua-hang");
  for (const [label, v] of Object.entries(values)) await main(page).getByLabel(label, { exact: true }).fill(v);
  await main(page).getByRole("button", { name: "Lưu thay đổi" }).click();
  await expect(page.getByText("Đã lưu thông tin cửa hàng")).toBeVisible();
}

test("đổi tên người chọn trong Cài đặt → lưu thật, trang «Về người chọn» đổi theo", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "luồng ghi dữ liệu chỉ chạy một lần");
  await login(page);
  await page.goto("/desk/cai-dat/cua-hang");
  const nameBox = main(page).getByLabel("Tên người chọn", { exact: true });
  const holderBox = main(page).getByLabel("Tên chủ tài khoản", { exact: true });
  await expect(nameBox).not.toHaveValue("");
  const before = { "Tên người chọn": await nameBox.inputValue(), "Tên chủ tài khoản": await holderBox.inputValue() };

  try {
    await saveStore(page, { "Tên người chọn": "Lan Thử", "Tên chủ tài khoản": "NGUYEN THI LAN THU" });
    await page.reload();
    await expect(main(page).getByLabel("Tên người chọn", { exact: true })).toHaveValue("Lan Thử");
    await expect(main(page).getByLabel("Tên chủ tài khoản", { exact: true })).toHaveValue("NGUYEN THI LAN THU");

    await page.goto("/ve-nguoi-chon");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Mình là Lan Thử");
  } finally {
    await saveStore(page, before);
  }
});
