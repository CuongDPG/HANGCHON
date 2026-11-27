import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import path from "node:path";

/**
 * Rà toàn bộ route của website và bàn làm việc trên dữ liệu mẫu (`app.seed --demo`, scripts/e2e.sh tự dựng):
 * mỗi trang có đúng một tiêu đề h1, không lỗi console, không tràn ngang, không còn trang giữ chỗ «đang xây».
 * Chỉ đọc, không ghi dữ liệu. E2E_SHOTS=1 để chụp ảnh từng trang vào test-results/shots/routes/.
 */

test.skip(!process.env.E2E_API, "Cần API + dữ liệu mẫu (E2E_API=1, xem scripts/e2e.sh)");

const OWNER = { email: process.env.E2E_OWNER_EMAIL ?? "chi@hangchon.local", password: process.env.E2E_OWNER_PASSWORD ?? "doimatkhau" };

type Ids = Record<string, string | undefined>;

async function first<T = Record<string, unknown>>(req: APIRequestContext, url: string, pick?: (x: T) => boolean): Promise<T | undefined> {
  const r = await req.get(url);
  if (!r.ok()) return undefined;
  const data = await r.json();
  const items: T[] = Array.isArray(data) ? data : (data.items ?? []);
  return pick ? items.find(pick) : items[0];
}

async function collectIds(req: APIRequestContext): Promise<Ids> {
  await req.post("/api/desk/auth/login", { data: OWNER });
  const ids: Ids = {};
  // món đã đăng trong dữ liệu mẫu (bài khác có thể đang tạo món nháp cùng lúc)
  const product = await first<{ id: string; slug: string; status: string }>(req, "/api/desk/catalog/products?size=100", (p) => p.status === "published");
  ids.product = product?.id;
  ids.slug = product?.slug;
  const drop = await first<{ id: string; slug: string; status: string }>(req, "/api/desk/catalog/drops?size=50", (d) => d.status === "open");
  ids.drop = drop?.id;
  ids.dropSlug = drop?.slug;
  ids.order = (await first<{ id: string }>(req, "/api/desk/orders?size=50"))?.id;
  ids.thread = (await first<{ id: string }>(req, "/api/desk/inbox/threads?tab=all"))?.id;
  ids.customer = (await first<{ id: string }>(req, "/api/desk/crm/customers"))?.id;
  ids.po = (await first<{ id: string }>(req, "/api/desk/supply/purchase-orders"))?.id;
  ids.lot = (await first<{ id: string }>(req, "/api/desk/supply/inbound"))?.id;
  ids.supplier = (await first<{ id: string }>(req, "/api/desk/supply/suppliers"))?.id;
  ids.brief = (await first<{ id: string }>(req, "/api/desk/sourcing/briefs"))?.id;
  ids.comparison = (await first<{ id: string }>(req, "/api/desk/assessment/comparisons"))?.id;
  ids.livestream = (await first<{ id: string }>(req, "/api/desk/content/livestreams"))?.id;
  const cand = await first<{ id: string }>(req, `/api/desk/sourcing/briefs/${ids.brief}/candidates?size=50`);
  ids.candidate = cand?.id;
  const board = await (await req.get("/api/desk/selection/board")).json();
  ids.selected = board.columns?.selected?.[0]?.id;
  // khách: theo dõi đơn đã giao (có link đánh giá) và link thử hàng
  const done = await first<{ id: string; code: string; recipient_phone: string; status: string }>(req, "/api/desk/orders?size=50&nhom=xong");
  if (done) {
    const lk = await req.post("/api/store/orders/lookup", { data: { phone: done.recipient_phone, code: done.code } });
    if (lk.ok()) {
      const { code, token } = await lk.json();
      ids.trackPath = `/don/${code}?t=${token}`;
      const pub = await (await req.get(`/api/store/orders/${code}`, { params: { t: token } })).json();
      ids.reviewToken = pub.reviews?.find((r: { status: string }) => r.status === "requested")?.token;
    }
  }
  const testers = await (await req.get("/api/desk/crm/testers/candidates")).json();
  const link: string | undefined = testers.flatMap((c: { invites: { link: string | null }[] }) => c.invites).find((i: { link: string | null }) => i.link)?.link;
  ids.testerPath = link ? new URL(link).pathname : undefined;
  // «Mời thử cùng»: lời mời riêng (link không liệt kê ở đâu) + màn desk của lời mời
  const offer = await first<{ id: string; link: string; status: string }>(req, "/api/desk/crm/cotrial/offers", (o) => o.status === "open");
  ids.offer = offer?.id;
  ids.offerPath = offer ? new URL(offer.link).pathname : undefined;
  return ids;
}

const STORE = (i: Ids) => [
  "/",
  i.slug && `/san-pham/${i.slug}`,
  "/dot",
  i.dropSlug && `/dot/${i.dropSlug}`,
  "/cua-toi",
  "/cua-toi?tab=don",
  "/dat-hang",
  i.trackPath,
  "/nho-tim",
  "/ve-nguoi-chon",
  "/hoi",
  i.reviewToken && `/danh-gia/${i.reviewToken}`,
  i.testerPath,
  "/dung-thu",
  i.offerPath,
];

const DESK = (i: Ids) => [
  "/desk",
  "/desk/san-hang",
  i.brief && `/desk/san-hang/de/${i.brief}`,
  i.candidate && `/desk/san-hang/ung-vien/${i.candidate}`,
  i.comparison && `/desk/san-hang/so-sanh/${i.comparison}`,
  "/desk/san-hang/khung-cham",
  "/desk/ban-chon",
  i.selected && `/desk/ban-chon/${i.selected}`,
  "/desk/ban-chon/nguyen-tac",
  "/desk/ban-chon/gu",
  "/desk/noi-dung",
  i.product && `/desk/noi-dung/san-pham/${i.product}`,
  i.drop && `/desk/noi-dung/dot/${i.drop}`,
  "/desk/noi-dung/lich",
  "/desk/noi-dung/giong",
  "/desk/noi-dung/so-lieu",
  "/desk/noi-dung/video",
  "/desk/noi-dung/livestream",
  i.livestream && `/desk/noi-dung/livestream/${i.livestream}`,
  "/desk/khach",
  i.thread && `/desk/khach/hoi-thoai/${i.thread}`,
  "/desk/khach/so-khach",
  i.customer && `/desk/khach/so-khach/${i.customer}`,
  "/desk/khach/khach-quen",
  "/desk/khach/nhac-mua-lai",
  "/desk/khach/gioi-thieu",
  "/desk/khach/thu-hang",
  "/desk/khach/dung-thu",
  "/desk/khach/dung-thu?tab=so",
  i.offer && `/desk/khach/dung-thu/${i.offer}`,
  "/desk/don-hang",
  i.order && `/desk/don-hang/${i.order}`,
  "/desk/don-hang/tao",
  "/desk/don-hang/van-hanh",
  "/desk/don-hang/in-nhan",
  "/desk/nguon-cung",
  i.po && `/desk/nguon-cung/don/${i.po}`,
  i.selected && `/desk/nguon-cung/gia-von/${i.selected}`,
  i.lot && `/desk/nguon-cung/lo/${i.lot}`,
  i.supplier && `/desk/nguon-cung/ncc/${i.supplier}`,
  "/desk/nguon-cung/cai-dat",
  "/desk/duyet",
  "/desk/tu-chu",
  "/desk/tu-chu/chi-phi-ai",
  "/desk/nhat-ky-ai",
  "/desk/bao-cao",
  "/desk/so-sach",
  "/desk/san-pham",
  i.product && `/desk/san-pham/${i.product}`,
  "/desk/san-pham/dot",
  i.drop && `/desk/san-pham/dot/${i.drop}`,
  "/desk/san-pham/danh-gia",
  "/desk/san-pham/nho-tim",
  "/desk/cai-dat",
  "/desk/cai-dat/cua-hang",
  "/desk/cai-dat/nguoi-phu-giup",
  "/desk/cai-dat/sao-luu",
  "/desk/cai-dat/tai-khoan",
  "/desk/cai-dat/tich-hop",
  "/desk/cai-dat/mang-xa-hoi",
  "/desk/cai-dat/ai",
];

function watch(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()} @ ${m.location().url}`);
  });
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500) errors.push(`api ${r.status()}: ${r.url()}`);
  });
  return errors;
}

async function check(page: Page, url: string, project: string, errors: string[]) {
  errors.length = 0;
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  const main = page.getByRole("main");
  await expect(main.locator("h1:visible").first(), `${url}: thiếu tiêu đề`).toBeVisible();
  expect(await main.locator("h1:visible").count(), `${url}: nhiều hơn một h1`).toBe(1);
  await expect(main.getByText(/đang xây|sắp có|Trang giữ chỗ/i), `${url}: còn trang giữ chỗ`).toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${url}: tràn ngang ${overflow}px`).toBeLessThanOrEqual(0);
  if (process.env.E2E_SHOTS) {
    const name = url.replace(/\?.*$/, "").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home";
    await page.screenshot({ path: path.join("test-results", "shots", "routes", `${project}-${name}.png`), fullPage: true });
  }
  expect(errors, `${url}: lỗi trên trang`).toEqual([]);
}

test("mọi trang website", async ({ page }, info) => {
  test.setTimeout(180_000);
  const ids = await collectIds(page.request);
  await page.context().clearCookies();
  const errors = watch(page);
  for (const url of STORE(ids).filter(Boolean) as string[]) await check(page, url, info.project.name, errors);
});

test("menu, chân trang, khẩu hiệu và «Của tôi» (link cũ /gio-hang, /don chuyển về)", async ({ page }, info) => {
  const menu = ["Kệ hàng", "Mua chung", "Nhờ tìm", "Dùng thử", "Của tôi"];
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: info.project.name === "mobile" ? "Điều hướng" : "Mục chính" });
  await expect(nav.getByRole("link")).toHaveText(menu);
  await expect(page.getByRole("navigation", { name: "Liên kết chân trang" }).getByRole("link")).toHaveText([
    ...menu,
    "Về Hàng Chọn",
    "Hỏi trợ lý",
  ]);
  const taglines: [string, string][] = [
    ["/", "Ít nhưng mà chất..."],
    ["/dot", "Mua chung để có giá tốt nhất..."],
    ["/nho-tim", "Mua cùng chuyên gia..."],
    ["/dung-thu", "Thử cùng, cho mình và cho mọi người..."],
  ];
  for (const [url, line] of taglines) {
    await page.goto(url);
    await expect(page.getByRole("main").getByRole("heading", { level: 1 }), url).toHaveText(line);
  }
  await page.goto("/gio-hang");
  await expect(page).toHaveURL(/\/cua-toi$/);
  await expect(page.getByRole("main").getByRole("tab", { name: /Giỏ hàng/, selected: true })).toBeVisible();
  await page.goto("/don");
  await expect(page).toHaveURL(/\/cua-toi\?tab=don$/);
  const main = page.getByRole("main");
  await expect(main.getByRole("tab", { name: "Đơn của tôi", selected: true })).toBeVisible();
  await expect(main.getByRole("heading", { name: "Đăng nhập để xem mọi đơn" })).toBeVisible();
  await expect(main.getByRole("heading", { name: "Tra một đơn bằng mã đơn" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "/cua-toi?tab=don: tràn ngang").toBeLessThanOrEqual(0);
  await main.getByRole("tab", { name: /Giỏ hàng/ }).click();
  await expect(page).toHaveURL(/\/cua-toi$/);
});

/**
 * Giọng với khách: người bán xưng «mình», gọi khách «bạn». «Chị» là cách gọi nội bộ ở bàn làm việc, không được lọt ra
 * website — kể cả tiêu đề, mô tả SEO, JSON-LD, nhãn ảnh/nút, nguồn cấp sản phẩm và trang 404.
 */
const CHI = /(^|[^\p{L}])chị(?!\p{L})/iu;

async function customerText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const attr = (sel: string, name: string) => [...document.querySelectorAll(sel)].map((el) => el.getAttribute(name) ?? "");
    return [
      document.title,
      document.body.innerText,
      ...attr('meta[name="description"], meta[property^="og:"], meta[name^="twitter:"]', "content"),
      ...[...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent ?? ""),
      ...attr("[aria-label]", "aria-label"),
      ...attr("[placeholder]", "placeholder"),
      ...attr("img[alt]", "alt"),
    ].join("\n");
  });
}

function chiLines(text: string): string[] {
  return text.split("\n").filter((l) => CHI.test(l));
}

test("website không gọi người bán là «chị»", async ({ page }) => {
  test.setTimeout(180_000);
  const ids = await collectIds(page.request);
  await page.context().clearCookies();
  const urls = [...(STORE(ids).filter(Boolean) as string[]), "/khong-co-trang-nay"];
  const found: string[] = [];
  for (const url of urls) {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    found.push(...chiLines(await customerText(page)).map((l) => `${url}: ${l.trim()}`));
  }
  // hỏi một câu trợ lý chưa có căn cứ → câu trả lời mẫu và nhãn «đã ghi lại»
  await page.goto("/hoi");
  await page.getByRole("main").getByRole("textbox", { name: "Câu hỏi" }).fill("Có bảo hành mấy năm không?");
  await page.getByRole("main").getByRole("button", { name: "Gửi câu hỏi" }).click();
  await expect(page.getByRole("main").getByText("Đã ghi lại, mình sẽ trả lời", { exact: true })).toBeVisible();
  found.push(...chiLines(await customerText(page)).map((l) => `/hoi (sau khi hỏi): ${l.trim()}`));
  const feed = await page.request.get("/feed.xml");
  if (feed.ok()) found.push(...chiLines(await feed.text()).map((l) => `/feed.xml: ${l.trim()}`));
  expect(found, "chữ «chị» trên website").toEqual([]);
});

test("mọi trang bàn làm việc", async ({ page }, info) => {
  test.setTimeout(300_000);
  const ids = await collectIds(page.request);
  const errors = watch(page);
  for (const url of DESK(ids).filter(Boolean) as string[]) await check(page, url, info.project.name, errors);
});
