import { expect, test, type Page } from "@playwright/test";

/**
 * Luồng chính trung tâm điều khiển + sổ sách, chạy trên API thật có dữ liệu mẫu:
 *   API chạy với HC_DEMO_ACTIONS=1, đã chạy seed (app.seed + control/finance seed_demo).
 *   E2E_API=1 E2E_EMAIL=… E2E_PASSWORD=… bun run e2e desk-control
 * Không có E2E_API thì bỏ qua (bài khói vẫn chạy khi API chưa bật).
 */
test.skip(!process.env.E2E_API, "cần API thật có dữ liệu mẫu (đặt E2E_API=1)");
test.describe.configure({ mode: "serial" });

async function login(page: Page) {
  await page.goto("/desk/dang-nhap");
  await page.getByLabel("Email").fill(process.env.E2E_EMAIL ?? "chi@hangchon.local");
  await page.getByLabel("Mật khẩu").fill(process.env.E2E_PASSWORD ?? "doimatkhau");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Hôm nay" })).toBeVisible();
}

const main = (page: Page) => page.getByRole("main");

test("Hôm nay → sửa rồi duyệt, trả lại, đổi mức tự chủ, hoàn tác, ghi chi phí, ra lệnh, báo cáo", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "luồng ghi dữ liệu chỉ chạy một lần");
  await login(page);

  // i1 + i2: mở việc chờ từ «Hôm nay», sửa rồi duyệt
  await expect(main(page).getByRole("heading", { level: 2, name: /việc chờ chị/ })).toBeVisible();
  // việc an toàn để duyệt trong dữ liệu mẫu: gợi ý mua mẫu (đơn nháp từ tin nhắn còn thiếu địa chỉ thì duyệt sẽ lỗi)
  const all = main(page).getByRole("button", { name: /Duyệt →/ });
  const safe = all.filter({ hasText: "Mua mẫu «" });
  const rows = (await safe.count()) ? safe : all;
  if (await rows.count()) {
    await rows.first().click();
    const sheet = page.getByRole("dialog");
    if (await sheet.getByRole("button", { name: "Sửa" }).count()) {
      await sheet.getByRole("button", { name: "Sửa" }).click();
      const field = sheet.locator("textarea, input").first();
      await field.fill(`${await field.inputValue()} (đã sửa)`);
      await sheet.getByRole("button", { name: "Duyệt bản đã sửa" }).click();
      await expect(page.getByText("Đã sửa và duyệt")).toBeVisible();
    } else {
      await sheet.getByRole("button", { name: "Duyệt", exact: true }).click();
      await expect(page.getByText("Đã duyệt", { exact: true })).toBeVisible();
    }
  }

  // i2: trả lại kèm lời nhắn ở hàng chờ
  await page.goto("/desk/duyet");
  await expect(page.getByRole("heading", { level: 1, name: "Chờ duyệt" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  const pending = main(page).getByRole("button", { name: /Duyệt →|Xử lý →/ });
  if (await pending.count()) {
    await pending.first().click();
    const sheet = page.getByRole("dialog");
    await sheet.getByRole("button", { name: "Trả lại" }).click();
    await sheet.getByLabel("Lời nhắn cho AI").fill("Viết ngắn lại, bỏ câu nói quá");
    await sheet.getByRole("button", { name: "Gửi lời nhắn" }).click();
    await expect(page.getByText("Đã trả lại cho AI kèm lời nhắn")).toBeVisible();
  }

  // i3: đổi mức một việc rồi trả về như cũ
  await page.goto("/desk/tu-chu");
  const group = main(page).getByRole("radiogroup").first();
  await expect(group).toBeVisible();
  const before = await group.getByRole("radio", { checked: true }).innerText();
  await group.getByRole("radio", { name: "Tắt" }).click();
  await expect(group.getByRole("radio", { name: "Tắt" })).toHaveAttribute("aria-checked", "true");
  await group.getByRole("radio", { name: before }).click();
  await expect(main(page).getByText(/Trần chi phí AI|Chi phí AI/).first()).toBeVisible();

  // i4: hoàn tác một việc AI tự làm
  await page.goto("/desk/nhat-ky-ai?ngay=30-ngay");
  await expect(main(page).getByRole("button", { name: /Căn cứ/ }).first()).toBeVisible();
  const undo = main(page).getByRole("button", { name: "Hoàn tác" });
  if (!(await undo.count())) await main(page).getByRole("button", { name: "Cũ hơn →" }).click();
  await expect(undo.first()).toBeVisible();
  {
    // hoàn tác việc cũ nhất trên trang (của dữ liệu mẫu), không đụng việc mới do bài chạy song song vừa tạo
    // (vd. bài vòng đời: hoàn tác «lưu ứng viên» sẽ xoá ứng viên nó đang mở)
    await undo.last().click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Hoàn tác" }).click();
    await expect(page.getByText("Đã hoàn tác").first()).toBeVisible();
  }
  await main(page).getByRole("tab", { name: "Lưu vết duyệt" }).click();
  await expect(main(page).getByText(/Duyệt|Trả lại|Hoàn tác/).first()).toBeVisible();

  // k1: ghi khoản chi kèm ảnh chứng từ
  await page.goto("/desk/so-sach?tab=chi-phi");
  await main(page).getByRole("button", { name: "Ghi khoản chi" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("Số tiền").fill("125000");
  await form.getByLabel("Chi cho việc gì").fill("Băng keo đóng gói (thử e2e)");
  await form.getByLabel("Chọn ảnh chứng từ").setInputFiles({ name: "bien-lai.png", mimeType: "image/png", buffer: Buffer.from("89504e470d0a1a0a", "hex") });
  await form.getByRole("button", { name: "Ghi vào sổ" }).click();
  await expect(page.getByText("Đã ghi khoản chi vào sổ")).toBeVisible();
  await expect(main(page).getByText("Băng keo đóng gói (thử e2e)").first()).toBeVisible();

  // i6: ra lệnh bằng lời (gõ)
  await page.getByRole("button", { name: "Nói với AI" }).click();
  const cmd = page.getByRole("dialog");
  await cmd.getByLabel("Lệnh cho AI").fill("có việc gì chờ chị duyệt không");
  await cmd.getByRole("button", { name: "Gửi cho AI" }).click();
  await expect(cmd.getByText(/Đã giao|Em cần chị nói rõ hơn/)).toBeVisible();
  await cmd.getByRole("button", { name: "Đóng" }).click();

  // i5: lập lại báo cáo tuần này
  await page.goto("/desk/bao-cao");
  await main(page).getByRole("button", { name: "Lập lại tuần này" }).click();
  await expect(page.getByText("Đã lập báo cáo tuần này")).toBeVisible();
  await expect(main(page).getByText("AI rút ra")).toBeVisible();
});

test("các màn bàn làm việc không tràn ngang", async ({ page }) => {
  await login(page);
  for (const path of ["/desk", "/desk/duyet", "/desk/tu-chu", "/desk/tu-chu/chi-phi-ai", "/desk/nhat-ky-ai", "/desk/bao-cao", "/desk/so-sach", "/desk/cai-dat", "/desk/cai-dat/cua-hang", "/desk/cai-dat/sao-luu"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${path} tràn ngang`).toBeLessThanOrEqual(0);
  }
});
