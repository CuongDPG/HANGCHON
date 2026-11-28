import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * Nút «Gửi sang Hàng Chọn»: lấy đúng bookmarklet ở Cài đặt → Nguồn hàng, chạy trên một trang 1688 giả (trang tự viết,
 * chặn mạng thật bằng route), cửa sổ /desk/kep nhận dữ liệu ở phần # → thêm ứng viên lẻ; gửi lại cùng món → cập nhật.
 */
test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
const FIXTURE = readFileSync(path.join(__dirname, "..", "src", "lib", "clipper", "fixtures", "1688.html"), "utf8");
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

test("gửi trang 1688 sang Hàng Chọn: thêm ứng viên lẻ, gửi lại thì cập nhật", async ({ page, context }, info) => {
  test.skip(info.project.name !== "desktop", "Nút trên thanh dấu trang dành cho máy tính");
  test.setTimeout(120_000);
  expect((await page.request.post("/api/desk/auth/login", { data: OWNER })).ok()).toBe(true);
  const offer = String(Date.now()).slice(-12);
  const productUrl = `https://detail.1688.com/offer/${offer}.html?spm=a1`;
  await context.route("https://detail.1688.com/**", (r) => r.fulfill({ contentType: "text/html; charset=utf-8", body: FIXTURE }));
  await context.route(/alicdn\.com/, (r) => r.fulfill({ contentType: "image/png", body: PNG }));

  // ---- nút ở Cài đặt → Nguồn hàng là một javascript: URL ------------------------------------------------------
  await page.goto("/desk/cai-dat/nguon-hang");
  const card = page.getByRole("main").getByRole("region", { name: "Nút Gửi sang Hàng Chọn" });
  const button = card.getByText("Gửi sang Hàng Chọn", { exact: true });
  await expect(button).toBeVisible();
  await expect.poll(() => button.evaluate((el) => el.closest("a")?.getAttribute("href") ?? "")).toMatch(/^javascript:/);
  const href = await button.evaluate((el) => el.closest("a")!.getAttribute("href")!);
  const code = decodeURIComponent(href.slice("javascript:".length));

  // ---- chạy nút trên trang sàn → cửa sổ /desk/kep -----------------------------------------------------------------
  await page.goto(productUrl);
  const [popup] = await Promise.all([page.waitForEvent("popup"), page.evaluate((c) => (0, eval)(c), code)]);
  await expect(popup.getByRole("heading", { level: 1, name: "Gửi sang Hàng Chọn" })).toBeVisible();
  await expect(popup).toHaveURL(/\/desk\/kep$/); // phần # đã được xoá khỏi thanh địa chỉ
  await expect(popup.getByRole("heading", { name: "不锈钢折叠晾衣架 阳台落地 加厚" })).toBeVisible();
  await expect(popup.getByText("1688", { exact: true })).toBeVisible();
  await expect(popup.getByText(`mã ${offer}`)).toBeVisible();
  await expect(popup.getByRole("list", { name: /\d+ ảnh/ }).locator("li")).toHaveCount(4);
  await popup.getByRole("button", { name: "Thêm ứng viên lẻ" }).click();
  await expect(popup.getByText("Đã thêm ứng viên")).toBeVisible({ timeout: 30_000 });
  const profile = await popup.getByRole("link", { name: "Mở hồ sơ" }).getAttribute("href");
  const cid = profile!.split("/").pop()!;

  const c = await (await page.request.get(`/api/desk/sourcing/candidates/${cid}`)).json();
  expect(c).toMatchObject({ source_platform: "1688", source_external_id: offer, source_url: `https://detail.1688.com/offer/${offer}.html`, seller_name: "义乌某某家居厂", moq: 2 });
  expect(c.images[0]).toBe("https://cbu01.alicdn.com/img/ibank/O1CN01aaa_!!2200-0-cib.jpg");
  const g = await (await page.request.get(`/api/desk/sourcing/candidates/${cid}/gallery`)).json();
  expect(g.detail_fetch).toMatchObject({ status: "done", error: null });

  // ---- gửi lại cùng món (cửa sổ cũ còn mở, chỉ đổi phần #) → cập nhật ứng viên đã có -----------------------------
  await page.evaluate((c) => (0, eval)(c), code);
  await expect(popup.getByRole("button", { name: "Cập nhật ứng viên" })).toBeVisible();
  await expect(popup.getByRole("link", { name: c.title_vi })).toHaveAttribute("href", `/desk/san-hang/ung-vien/${cid}`);
  await popup.getByRole("button", { name: "Cập nhật ứng viên" }).click();
  await expect(popup.getByText("Đã cập nhật ứng viên")).toBeVisible({ timeout: 30_000 });
  await expect(popup.getByRole("link", { name: "Mở hồ sơ" })).toHaveAttribute("href", `/desk/san-hang/ung-vien/${cid}`);

  // ---- hồ sơ ứng viên hiện ảnh vừa gửi -----------------------------------------------------------------------------
  await page.goto(`/desk/san-hang/ung-vien/${cid}`);
  await expect(page.getByRole("main").getByRole("region", { name: "Ảnh nhà cung cấp" }).getByRole("button", { name: /Xem ảnh/ }).first()).toBeVisible();
});
