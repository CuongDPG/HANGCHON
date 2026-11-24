import { expect, test, type Page } from "@playwright/test";

/**
 * Luồng chính khu Khách (h1–h8) trên dữ liệu thật của API (driver mock, AI fake):
 * tin khách đến → AI soạn nháp → chị gửi; sổ khách tìm không dấu; khách gửi cảm nhận qua link thử hàng.
 * Cần API đang chạy với dữ liệu mẫu (`uv run python -m app.seed --demo`, scripts/e2e.sh tự dựng) và tài khoản chị mặc định;
 * không có thì bài này tự bỏ qua. Đổi tài khoản bằng E2E_OWNER_EMAIL / E2E_OWNER_PASSWORD.
 */

const EMAIL = process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local";
const PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "doimatkhau";

async function login(page: Page) {
  const health = await page.request.get("/api/health").catch(() => null);
  test.skip(!health?.ok(), "API chưa chạy");
  const r = await page.request.post("/api/desk/auth/login", { data: { email: EMAIL, password: PASSWORD } });
  test.skip(!r.ok(), "Chưa có tài khoản chị trên API");
  const meta = await page.request.get("/api/desk/inbox/meta");
  test.skip(!(await meta.json()).simulate_enabled, "API không bật giả lập tin đến");
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "trang bị tràn ngang").toBeLessThanOrEqual(0);
}

test("tin khách đến → AI soạn → chị sửa và gửi", async ({ page }) => {
  await login(page);
  const sim = await page.request.post("/api/desk/inbox/dev/simulate", {
    data: { text: "Khăn tắm cho bé giá bao nhiêu shop?", channel: "facebook", kind: "direct_message", author_name: `Khách E2E ${Date.now()}` },
  });
  expect(sim.ok()).toBeTruthy();
  const thread = await sim.json();

  await page.goto("/desk/khach");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Hộp thư" })).toBeVisible();
  await expect(main.getByRole("tab", { name: /Chờ chị/ })).toHaveAttribute("aria-selected", "true");
  await expect(main.getByText(thread.participant_name)).toBeVisible();
  await noOverflow(page);

  await page.goto(`/desk/khach/hoi-thoai/${thread.id}`);
  await expect(main.getByText("Khăn tắm cho bé giá bao nhiêu shop?")).toBeVisible();
  await expect(main.getByText(/189\.000đ/).first()).toBeVisible();
  await main.getByRole("button", { name: "Sửa" }).click();
  await main.getByRole("textbox", { name: "Câu trả lời" }).fill("Dạ khăn tắm cho bé giá 189.000đ ạ, đợt sau mình về thêm.");
  await main.getByRole("button", { name: "Gửi", exact: true }).first().click();
  await expect(page.getByText("Đã gửi cho khách")).toBeVisible();
  await expect(main.getByText("Dạ khăn tắm cho bé giá 189.000đ ạ, đợt sau mình về thêm.")).toBeVisible();
  await expect(main.getByText(/Chị gửi · AI soạn/)).toBeVisible();
  await noOverflow(page);
});

test("sổ khách tìm không dấu và mở hồ sơ", async ({ page }) => {
  await login(page);
  await page.goto("/desk/khach/so-khach");
  const main = page.getByRole("main");
  await main.getByRole("searchbox", { name: "Tìm khách" }).fill("pham ngoc lan");
  await main.getByRole("link", { name: /Phạm Ngọc Lan/ }).click();
  await expect(main.getByRole("heading", { level: 1, name: "Phạm Ngọc Lan" })).toBeVisible();
  await expect(main.getByText("AI tóm tắt")).toBeVisible();
  await noOverflow(page);
});

test("khách gửi cảm nhận thử hàng qua link một lần", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "Link dùng một lần: chỉ chạy ở một khổ màn hình");
  await login(page);
  const cands = await (await page.request.get("/api/desk/crm/testers/candidates")).json();
  const invite = cands.flatMap((c: { invites: { status: string; link: string }[] }) => c.invites).find((i: { status: string }) => i.status === "sample_sent");
  test.skip(!invite, "Không còn lời mời nào chờ cảm nhận (dữ liệu mẫu đã dùng)");
  const path = new URL(invite.link).pathname;
  await page.context().clearCookies();
  await page.goto(path);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Thử hàng cùng mình" })).toBeVisible();
  await main.getByRole("radio", { name: "4 sao" }).click();
  await main.getByRole("textbox", { name: /thấy món này thế nào/ }).fill("Lọc nhanh, nước ngon. Vòi hơi lỏng.");
  await main.getByRole("button", { name: "Gửi cảm nhận" }).click();
  await expect(main.getByText("Cảm ơn bạn đã kể thật lòng!")).toBeVisible();
  await noOverflow(page);
});
