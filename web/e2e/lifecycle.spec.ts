import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Vòng đời trọn vẹn một món hàng qua giao diện (scripts/e2e.sh tự dựng API + worker + web + dữ liệu mẫu; AI giả,
 * driver giả). Bước nào có màn hình thì bấm trên màn hình; bước chỉ là «tới giờ» (tiền về, lô hàng về, hãng giao)
 * thì giả lập qua API/driver mock. Mỗi bước kiểm dữ liệu thật trên màn hình hoặc API.
 *
 * ra đề → quét → thẩm định → mua mẫu (đơn mẫu chờ duyệt, chị duyệt) → đang thử, ghi chú → Đã chọn, chị chốt lời →
 * sản phẩm nháp → giá vốn, chị duyệt giá → đăng lên kệ → bài các kênh, chị duyệt, tới giờ đăng → mở đợt → khách thấy
 * con dấu, lý do chọn → giỏ, đặt, chuyển khoản → đã trả, sổ doanh thu → khách nhắn, chị gửi → chốt đợt sớm → đơn đặt
 * nguồn, chị duyệt → lô về → tạo vận đơn → giao xong → khách đánh giá, chị cho hiện → Hôm nay, nhật ký AI, báo cáo.
 */

test.skip(!process.env.E2E_API, "Cần API + worker + dữ liệu mẫu (scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };
const RUN = `${Date.now() % 100000}`;

async function api<T = Record<string, unknown>>(req: APIRequestContext, method: "get" | "post" | "patch", url: string, data?: unknown): Promise<T> {
  const r = await req[method](url, data === undefined ? undefined : { data });
  expect(r.ok(), `${method.toUpperCase()} ${url} → ${r.status()} ${await r.text()}`).toBe(true);
  return (await r.json()) as T;
}

async function login(page: Page) {
  await api(page.request, "post", "/api/desk/auth/login", OWNER);
}

/** Chị mở việc chờ ở «Chờ duyệt» (link `?id=` như khi bấm từ «Hôm nay») và bấm Duyệt. */
async function approveInQueue(page: Page, itemId: string, title: RegExp | string) {
  await page.goto(`/desk/duyet?id=${itemId}`);
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText(title).first()).toBeVisible({ timeout: 20_000 });
  await sheet.getByRole("button", { name: "Duyệt", exact: true }).click();
  await expect(page.getByText("Đã duyệt", { exact: true })).toBeVisible();
}

test("một món hàng từ đề tìm tới đánh giá của khách", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "Một luồng ghi dữ liệu, chạy ở khung điện thoại 390px");
  test.setTimeout(480_000);
  await login(page);
  const main = page.getByRole("main");

  // ---- a1/a4: ra đề bằng lời, AI hiểu, tìm --------------------------------------------------------------------
  await page.goto("/desk/san-hang");
  await page.getByLabel("Chị muốn tìm gì?").fill(`Tìm bình giữ nhiệt inox 304 cho bé đi học, nắp kín, giữ nóng lâu (lần ${RUN})`);
  await page.getByRole("button", { name: "AI đọc đề" }).click();
  await expect(page).toHaveURL(/\/desk\/san-hang\/de\//);
  const briefId = page.url().split("/de/")[1].split(/[?#]/)[0];
  // từ khoá riêng cho lần chạy này để nguồn giả trả món mới (không trùng ứng viên của lần trước)
  await api(page.request, "patch", `/api/desk/sourcing/briefs/${briefId}`, { keywords_translated: { zh: [`保温杯 ${RUN}${Math.round(Math.random() * 1e6)}`] } });
  await page.reload();
  await main.getByRole("button", { name: "Đúng rồi, tìm đi" }).click();
  const firstCand = main.locator('a[href^="/desk/san-hang/ung-vien/"]').first();
  await expect(firstCand.or(main.getByText("Chưa có ứng viên")).first()).toBeVisible({ timeout: 60_000 });
  // nguồn giả trả món ngẫu nhiên theo từ khoá; lỡ cả lượt bị lọc hết (giá, chất liệu) thì đổi từ khoá, tìm lại
  for (let i = 0; i < 5 && !(await firstCand.isVisible()); i++) {
    await api(page.request, "patch", `/api/desk/sourcing/briefs/${briefId}`, { keywords_translated: { zh: [`保温杯 ${RUN}-${i}${Math.round(Math.random() * 1e6)}`] } });
    await api(page.request, "post", `/api/desk/sourcing/briefs/${briefId}/run`);
    await page.reload();
    await expect(firstCand.or(main.getByText("Chưa có ứng viên")).first()).toBeVisible({ timeout: 30_000 });
  }
  await expect(firstCand).toBeVisible();
  await firstCand.click();

  // ---- b1–b7: hồ sơ thẩm định, chấm điểm theo khung --------------------------------------------------------
  await expect(page).toHaveURL(/\/desk\/san-hang\/ung-vien\//);
  const candId = page.url().split("/ung-vien/")[1].split(/[?#]/)[0];
  const start = main.getByRole("button", { name: "Thẩm định món này" });
  await expect(main.getByText("Điểm theo khung của chị").or(start).first()).toBeVisible({ timeout: 30_000 }); // trang đã tải xong
  if (await start.isVisible()) await start.click();
  await expect(main.getByText("Điểm theo khung của chị")).toBeVisible({ timeout: 60_000 });
  const title = (await main.getByRole("heading", { level: 1 }).textContent())!.trim();

  // ---- d5: mua mẫu → đơn đặt mẫu vào hàng chờ (luôn hỏi chị) → chị duyệt ---------------------------------------
  await main.getByRole("button", { name: "Mua mẫu", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Mua mẫu" }).click();
  await expect.poll(async () => (await api<{ items: unknown[] }>(page.request, "get", `/api/desk/supply/purchase-orders?candidate_id=${candId}`)).items.length).toBe(1);
  const samplePo = (await api<{ items: { id: string; code: string; approval_item_id: string }[] }>(page.request, "get", `/api/desk/supply/purchase-orders?candidate_id=${candId}`)).items[0];
  // từ việc chờ bấm «Mở chi tiết» tới đúng màn hình đơn đặt mẫu
  await page.goto(`/desk/duyet?id=${samplePo.approval_item_id}`);
  await page.getByRole("dialog").getByRole("link", { name: "Mở chi tiết →" }).click();
  await expect(page).toHaveURL(new RegExp(`/desk/nguon-cung/don/${samplePo.id}`));
  await expect(main.getByText(samplePo.code).first()).toBeVisible();
  await approveInQueue(page, samplePo.approval_item_id, samplePo.code);
  expect((await api<{ status: string }>(page.request, "get", `/api/desk/supply/purchase-orders/${samplePo.id}`)).status).toBe("approved");

  // ---- c1/c2: đang thử, ghi chú thử hàng ----------------------------------------------------------------------
  await api(page.request, "post", `/api/desk/selection/candidates/${candId}/stage`, { to: "trial" });
  await page.goto(`/desk/ban-chon/${candId}`);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  const notes = ["Rót nước sôi buổi sáng, chiều vẫn còn ấm.", "Nắp kín, lật ngược không rỉ.", "Hộp giấy hơi móp khi giao."];
  for (const [i, note] of notes.entries()) {
    await page.getByLabel("Ghi chú thử hàng").fill(note);
    await page.getByRole("button", { name: "Lưu ghi chú" }).click();
    await expect.poll(async () => (await api<unknown[]>(page.request, "get", `/api/desk/selection/candidates/${candId}/notes`)).length).toBe(i + 1);
  }
  await expect(main.getByText(/Ghi chú thử · 3/)).toBeVisible();

  // ---- c3: đóng dấu Đã chọn → AI soạn lý do → chị sửa lời rồi chốt → sản phẩm nháp tự sinh (e1) --------------------
  await page.getByRole("button", { name: "Đóng dấu Đã chọn" }).click();
  await expect(page.getByRole("heading", { name: "Vì sao mình chọn", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sửa lời rồi chốt" }).click();
  const sheet = page.getByRole("dialog", { name: "Sửa lời của chị" });
  await sheet.getByLabel("Ý 1").fill("Giữ ấm tới chiều.");
  await sheet.getByRole("button", { name: "Chốt lời" }).click();
  await expect(page.getByText("Chị đã chốt lời")).toBeVisible();
  const findProduct = async () =>
    (await api<{ decision: { product_id: string | null } | null }>(page.request, "get", `/api/desk/selection/candidates/${candId}`)).decision?.product_id;
  await expect.poll(findProduct, { timeout: 30_000 }).toBeTruthy();
  const productId = (await findProduct())!;

  // ---- d2/d3: giá vốn về tay + đề xuất giá → chị duyệt giá trong hàng chờ --------------------------------------
  await api(page.request, "post", "/api/desk/supply/cost-sheets", { candidate_id: candId, unit_price_amount: "38", currency: "CNY", weight_grams: 300 });
  await page.goto(`/desk/nguon-cung/gia-von/${candId}`);
  await expect(main.getByText(/Giá vốn về tay|về tay/).first()).toBeVisible();
  const proposal = await api<{ approval_item_id: string }>(page.request, "post", "/api/desk/supply/price-proposals", { candidate_id: candId });
  await approveInQueue(page, proposal.approval_item_id, `Giá bán ${title}`);
  await expect.poll(async () => (await api<{ price_vnd: number }>(page.request, "get", `/api/desk/catalog/products/${productId}`)).price_vnd).toBeGreaterThan(0);

  // ---- e1: AI viết trang (worker) → chị đăng lên kệ → content soạn bài các kênh (f1) ----------------------------
  await expect.poll(async () => (await api<{ status: string }>(page.request, "get", `/api/desk/catalog/products/${productId}`)).status, { timeout: 45_000 }).toBe("pending_review");
  await page.goto(`/desk/san-pham/${productId}`);
  await page.getByRole("button", { name: "Đăng lên kệ" }).click();
  await expect(page.getByText("Đã đăng lên kệ")).toBeVisible();
  const product = await api<{ slug: string; name: string; price_vnd: number }>(page.request, "get", `/api/desk/catalog/products/${productId}`);

  // ---- f1/f5/f3/f4: bài Facebook đã soát lời → chị duyệt, xếp lịch → đăng (driver giả) ---------------------------
  await page.goto(`/desk/noi-dung/san-pham/${productId}`);
  await expect(main.getByRole("tab", { name: /Facebook/ })).toBeVisible({ timeout: 45_000 });
  await main.getByRole("tab", { name: /Facebook/ }).click();
  await main.getByRole("button", { name: "Duyệt, xếp lịch" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Duyệt, xếp lịch" }).click();
  await expect(main.getByRole("tab", { name: "Facebook ✓" })).toBeVisible();
  const studio = await api<{ drafts: { channel: string; post: { id: string } | null }[] }>(page.request, "get", `/api/desk/content/studio/product/${productId}`);
  const postId = studio.drafts.find((d) => d.channel === "facebook")!.post!.id;
  const published = await api<{ status: string; external_url: string | null }>(page.request, "post", `/api/desk/content/posts/${postId}/publish-now`);
  expect(published.status).toBe("published");

  // ---- e3: mở đợt ------------------------------------------------------------------------------------------------
  const drop = await api<{ id: string; slug: string; code: string }>(page.request, "post", "/api/desk/catalog/drops", {
    title: `Đợt thử vòng đời ${RUN}`,
    closes_at: new Date(Date.now() + 3 * 86400_000).toISOString(),
    expected_arrival_date: new Date(Date.now() + 20 * 86400_000).toISOString().slice(0, 10),
    items: [{ product_id: productId, slots_total: 20, max_per_order: 3 }],
  });
  await page.goto(`/desk/san-pham/dot/${drop.id}`);
  await page.getByRole("button", { name: "Mở đợt" }).click();
  await expect(page.getByText("Đã mở đợt")).toBeVisible();

  // ---- e2: hồ sơ chọn đầy đủ chỉ ở desk (dải số sàng lọc + món đã loại) --------------------------------------------
  await page.goto(`/desk/san-pham/${productId}`);
  await expect(main.getByText("Mẫu A (đã chọn)", { exact: false })).toBeVisible();
  await expect(main.getByText("đã xem", { exact: true })).toBeVisible();

  // ---- e2/e4/g2: khách thấy con dấu + lý do chọn (không thấy quá trình chọn) → giỏ → đặt → chuyển khoản -------------
  await page.context().clearCookies();
  await page.goto(`/san-pham/${product.slug}?src=${postId.replace(/-/g, "").slice(0, 8)}`);
  await expect(main.getByRole("heading", { level: 1, name: product.name })).toBeVisible();
  await expect(main.getByRole("img", { name: /Đã chọn 1 trong/ }).first()).toBeVisible();
  await expect(main.getByText("Giữ ấm tới chiều.").first()).toBeVisible();
  await expect(main.getByRole("link", { name: "Xem hồ sơ chọn" })).toHaveCount(0);
  await page.getByRole("region", { name: "Đặt mua" }).filter({ visible: true }).first().getByRole("button", { name: /Đặt ngay|Đặt mua chung/ }).click();
  await expect(page).toHaveURL(/\/(gio-hang|dat-hang)/);
  if (page.url().includes("/gio-hang")) await main.getByRole("link", { name: "Đặt hàng" }).click();
  await main.getByLabel("Số điện thoại").fill("0900000777");
  await main.getByLabel("Họ tên").fill("Khách Vòng Đời");
  await main.getByLabel("Địa chỉ nhận hàng").fill("12 Ngõ Ví Dụ");
  await main.getByLabel("Tỉnh/thành").fill("Hà Nội");
  await main.getByRole("button", { name: "Đặt hàng" }).filter({ visible: true }).click();
  await expect(page).toHaveURL(/\/don\/HC-\d{5}\?t=/);
  const trackUrl = page.url();
  const code = decodeURIComponent(new URL(trackUrl).pathname.split("/").pop()!);
  const content = await page.getByText(/^HC \d{5}$/).first().textContent();
  const due = Number((await page.getByText("Số tiền").locator("..").textContent())!.replace(/\D/g, ""));
  await login(page);
  await api(page.request, "post", "/api/desk/orders/payments/simulate", { amount_vnd: due, content: `${content} chuyen tien` });
  await expect(page.getByText("Đã nhận đơn, đã thanh toán")).toBeVisible({ timeout: 15_000 });

  // ---- đã trả: đơn chờ hàng về, khách nhận tin, sổ doanh thu có dòng ------------------------------------------
  const orders = await api<{ items: { id: string; code: string; status: string }[] }>(page.request, "get", `/api/desk/orders?q=${encodeURIComponent(code)}`);
  const orderId = orders.items[0].id;
  const detail = await api<{ status: string; notifications: { event: string }[]; total_vnd: number }>(page.request, "get", `/api/desk/orders/${orderId}`);
  expect(detail.status).toBe("awaiting_stock");
  expect(detail.notifications.length).toBeGreaterThan(0);
  await page.goto("/desk/so-sach");
  await expect(main.getByText(code).first()).toBeVisible();

  // ---- h1/h2: khách nhắn hỏi → AI soạn → chị gửi ------------------------------------------------------------
  const thread = await api<{ id: string }>(page.request, "post", "/api/desk/inbox/dev/simulate", {
    text: `${product.name} giữ nhiệt được bao lâu ạ?`, channel: "facebook", kind: "direct_message", author_name: `Khách Hỏi ${RUN}`,
  });
  await page.goto(`/desk/khach/hoi-thoai/${thread.id}`);
  await expect(main.getByText(/giữ nhiệt được bao lâu/)).toBeVisible();
  await main.getByRole("button", { name: "Gửi", exact: true }).first().click();
  await expect(page.getByText("Đã gửi cho khách")).toBeVisible();

  // ---- g3: chốt đợt sớm (màn Đơn hàng) → đơn đặt nguồn soạn sẵn → chị duyệt ---------------------------------------
  await page.goto("/desk/don-hang");
  await main.getByRole("button", { name: `Chốt đợt sớm ${drop.code}` }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Chốt đợt" }).click();
  await expect(page.getByText(/Đã chốt/)).toBeVisible();
  const pos = await api<{ items: { id: string; code: string; kind: string; drop_id: string; approval_item_id: string }[] }>(page.request, "get", "/api/desk/supply/purchase-orders?size=100");
  const batch = pos.items.find((p) => p.drop_id === drop.id && p.kind === "batch")!;
  await approveInQueue(page, batch.approval_item_id, batch.code);
  expect((await api<{ status: string }>(page.request, "get", `/api/desk/supply/purchase-orders/${batch.id}`)).status).toBe("approved");

  // ---- d7: gửi đơn, lô hàng về → đơn chờ giao -----------------------------------------------------------------
  const sent = await api<{ inbound: { id: string }[] }>(page.request, "post", `/api/desk/supply/purchase-orders/${batch.id}/status`, { to: "sent" });
  for (const status of ["seller_shipped", "international_transit", "customs", "domestic_transit", "delivered"]) {
    await api(page.request, "post", `/api/desk/supply/inbound/${sent.inbound[0].id}/milestones`, { status });
  }
  await expect.poll(async () => (await api<{ status: string }>(page.request, "get", `/api/desk/orders/${orderId}`)).status).toBe("ready_to_ship");

  // ---- g4/g5: tạo vận đơn → hãng (giả) giao xong ------------------------------------------------------------------
  await page.goto(`/desk/don-hang/${orderId}`);
  await main.getByRole("button", { name: "Tạo vận đơn" }).click();
  await expect(page.getByText(/Đã tạo vận đơn/)).toBeVisible();
  const withShip = await api<{ shipments: { id: string }[] }>(page.request, "get", `/api/desk/orders/${orderId}`);
  await expect
    .poll(async () => {
      await api(page.request, "post", `/api/desk/orders/shipments/${withShip.shipments[0].id}/sync`);
      return (await api<{ status: string }>(page.request, "get", `/api/desk/orders/${orderId}`)).status;
    }, { timeout: 60_000, intervals: [2000] })
    .toBe("delivered");

  // ---- e8: khách nhận lời mời đánh giá trên trang theo dõi → gửi → chị cho hiện ---------------------------------
  await page.context().clearCookies();
  await page.goto(trackUrl);
  await main.getByRole("link", { name: "Viết đánh giá" }).first().click();
  await main.getByRole("radio", { name: "5 sao" }).click();
  await main.getByLabel("Bạn dùng thấy thế nào?").fill(`Giữ ấm tốt, nắp kín, bé dùng thích (vòng ${RUN}).`);
  await main.getByRole("button", { name: "Gửi đánh giá" }).click();
  await expect(main.getByText(/Cảm ơn/).first()).toBeVisible();
  await login(page);
  await page.goto("/desk/san-pham/danh-gia");
  const review = main.getByText(`vòng ${RUN}`).first().locator("xpath=ancestor::*[.//button[normalize-space()='Hiện']][1]");
  await review.getByRole("button", { name: "Hiện" }).first().click();
  await expect(page.getByText("Đã hiện trên trang sản phẩm")).toBeVisible();
  await page.context().clearCookies();
  await page.goto(`/san-pham/${product.slug}`);
  await expect(page.getByRole("main").getByText(`vòng ${RUN}`)).toBeVisible();

  // ---- i1/i4/i5: «Hôm nay», nhật ký AI, báo cáo tuần phản ánh đúng ----------------------------------------------
  await login(page);
  const today = await api<{ stats: { key: string; value: number }[]; pending: { total: number } }>(page.request, "get", "/api/desk/control/today");
  const stat = (k: string) => today.stats.find((s) => s.key === k)?.value ?? 0;
  expect(stat("orders.new_today")).toBeGreaterThanOrEqual(1);
  expect(stat("orders.cash_today")).toBeGreaterThanOrEqual(detail.total_vnd);
  expect(stat("control.pending")).toBe(today.pending.total);
  await page.goto("/desk");
  await expect(main.getByRole("heading", { level: 1, name: "Hôm nay" })).toBeVisible();
  await expect(main.getByRole("heading", { level: 2, name: new RegExp(`${today.pending.total} việc chờ chị`) })).toBeVisible();
  await page.goto(`/desk/nhat-ky-ai?ngay=hom-nay`);
  await expect(main.getByText(/Đăng bài|Soạn bài/).first()).toBeVisible();
  await page.goto("/desk/bao-cao");
  await main.getByRole("button", { name: "Lập lại tuần này" }).click();
  await expect(page.getByText("Đã lập báo cáo tuần này")).toBeVisible();
  const reports = await api<{ items: { revenue_vnd: number; week_start: string }[] }>(page.request, "get", "/api/desk/finance/reports");
  expect(reports.items[0].revenue_vnd).toBeGreaterThanOrEqual(detail.total_vnd);
});
