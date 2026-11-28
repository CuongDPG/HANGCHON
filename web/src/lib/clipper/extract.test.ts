// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { bookmarkletHref, bookmarkletSource, readClipHash } from "./bookmarklet";
import { clipPage, type ClipPayload } from "./extract";

const fixture = (name: string) => readFileSync(join(__dirname, "fixtures", name), "utf8");

function load(name: string): Document {
  return new DOMParser().parseFromString(fixture(name), "text/html");
}

// bản chuỗi (đúng thứ nằm trong bookmarklet) chạy trong phạm vi trống: hỏng nếu clipPage dùng biến/hàm ngoài thân hàm
const isolated = new Function(`return (${clipPage.toString()})`)() as typeof clipPage;

describe.each([
  ["thẳng", clipPage],
  ["bản chuỗi trong bookmarklet", isolated],
])("clipPage (%s)", (_, run) => {
  const read = (name: string, url: string): ClipPayload => run(load(name), url);

  it("1688: tên, giá, ảnh cỡ gốc, thông số, phân loại, người bán, số bán, MOQ", () => {
    const c = read("1688.html", "https://detail.1688.com/offer/712345678901.html?spm=x");
    expect(c.site).toBe("1688");
    expect(c.title).toBe("不锈钢折叠晾衣架 阳台落地 加厚");
    expect(c).toMatchObject({ price: "38.5", currency: "CNY", seller_name: "义乌某某家居厂", seller_url: "https://shop1234.1688.com/" });
    expect(c.images.slice(0, 3)).toEqual([
      "https://cbu01.alicdn.com/img/ibank/O1CN01aaa_!!2200-0-cib.jpg",
      "https://cbu01.alicdn.com/img/ibank/O1CN01bbb_!!2200-0-cib.jpg",
      "https://cbu01.alicdn.com/img/ibank/O1CN01ccc_!!2200-0-cib.jpg",
    ]);
    expect(c.images).toContain("https://cbu01.alicdn.com/img/ibank/O1CN01og_!!2200-0-cib.jpg");
    expect(c.images.every((u) => u.startsWith("https://"))).toBe(true);
    expect(c.specs).toMatchObject({ 材质: "不锈钢", 尺寸: "120cm", 品牌: "无" });
    expect(c.variants).toEqual(["颜色: 银色", "颜色: 黑色"]);
    expect(c).toMatchObject({ sales_count: 30500, moq: 2, rating: 4.5 });
  });

  it("Taobao: tên, giá, ảnh thu nhỏ → ảnh gốc, thông số, phân loại, cửa hàng, «已售 1万+»", () => {
    const c = read("taobao.html", "https://item.taobao.com/item.htm?id=681234567890");
    expect(c).toMatchObject({ site: "taobao", title: "硅胶厨房收纳盒 可折叠", price: "29.9", currency: "CNY", seller_name: "好物小店" });
    expect(c.seller_url).toBe("https://shop123.taobao.com/");
    expect(c.images).toEqual([
      "https://img.alicdn.com/imgextra/i1/2200/O1CN01x1_!!2200.jpg",
      "https://img.alicdn.com/imgextra/i2/2200/O1CN01x2_!!2200.jpg",
    ]);
    expect(c.specs).toEqual({ 材质: "硅胶" });
    expect(c.variants).toEqual(["绿色", "灰色"]);
    expect(c.sales_count).toBe(10000);
  });

  it("Amazon Nhật: giá khối mua (không lấy giá khác), ảnh hiRes/dynamic, đánh giá, thông số, gạch đầu dòng", () => {
    const c = read("amazon-jp.html", "https://www.amazon.co.jp/dp/B0ABCDEF12?th=1");
    expect(c).toMatchObject({ site: "amazon_jp", title: "折りたたみ 物干し ステンレス 室内", price: "2980", currency: "JPY" });
    expect(c.images).toEqual([
      "https://m.media-amazon.com/images/I/61Main.jpg",
      "https://m.media-amazon.com/images/I/81Hi.jpg",
      "https://m.media-amazon.com/images/I/71Alt.jpg",
    ]);
    expect(c).toMatchObject({ rating: 4.3, review_count: 1234, seller_name: "ほしもの商店" });
    expect(c.seller_url).toBe("https://www.amazon.co.jp/gp/help/seller/at-a-glance.html?seller=A1");
    expect(c.specs).toEqual({ 素材: "ステンレス", 色: "シルバー" });
    expect(c.description).toBe("耐荷重 15kg\n折りたたみ式");
    expect(c.variants).toEqual(["シルバー を選択"]);
  });

  it("Rakuten: tên, giá, ảnh (bỏ ?_ex=, ?fitin=), cửa hàng theo đường dẫn, đánh giá", () => {
    const c = read("rakuten.html", "https://item.rakuten.co.jp/kurashi/mat-01/");
    expect(c).toMatchObject({ site: "rakuten", title: "珪藻土 バスマット 大判", price: "1980", currency: "JPY", seller_name: "くらし雑貨店" });
    expect(c.seller_url).toBe("https://www.rakuten.co.jp/kurashi/");
    expect(c.images).toEqual([
      "https://tshop.r10s.jp/kurashi/cabinet/mat02.jpg",
      "https://image.rakuten.co.jp/kurashi/cabinet/mat03.jpg",
      "https://image.rakuten.co.jp/kurashi/cabinet/mat01.jpg",
    ]);
    expect(c).toMatchObject({ review_count: 523, rating: 4.62 });
  });

  it("trang lạ: JSON-LD Product (@graph) + og:image tương đối", () => {
    const c = read("generic.html", "https://shop.example.com/products/hop-gia-vi");
    expect(c).toMatchObject({ site: "web", title: "Hộp đựng gia vị 6 ngăn", price: "159000", currency: "VND", rating: 4.7, review_count: 88 });
    expect(c.images).toEqual(["https://shop.example.com/media/hop-1.jpg", "https://shop.example.com/media/hop-2.jpg"]);
    expect(c.description).toBe("Nhựa PP, nắp lật.");
    expect(c.seller_name).toBe("Mẫu");
  });

  it("trang trống: không đoán, chỉ lấy tiêu đề trang", () => {
    const doc = new DOMParser().parseFromString("<html><head><title>Một trang</title></head><body><img src='http://x.test/a.svg'></body></html>", "text/html");
    const c = run(doc, "https://x.test/p");
    expect(c).toMatchObject({ title: "Một trang", price: null, currency: null, images: [], specs: {}, variants: [] });
  });
});

describe("bookmarklet", () => {
  it("là một javascript: URL tự đủ, mở cửa sổ /desk/kep với dữ liệu ở phần #", () => {
    const href = bookmarkletHref("https://hangchon.vn");
    expect(href.startsWith("javascript:")).toBe(true);
    const code = decodeURIComponent(href.slice("javascript:".length));
    expect(code).toBe(bookmarkletSource("https://hangchon.vn"));
    // chạy thử trên trang Amazon giả: bắt window.open
    const opened: string[] = [];
    const doc = load("amazon-jp.html");
    new Function("document", "location", "window", "encodeURIComponent", code)(
      doc,
      { href: "https://www.amazon.co.jp/dp/B0ABCDEF12" },
      { open: (u: string) => (opened.push(u), {}) },
      encodeURIComponent,
    );
    expect(opened).toHaveLength(1);
    const [base, hash] = opened[0].split("#");
    expect(base).toBe("https://hangchon.vn/desk/kep");
    const data = readClipHash("#" + hash);
    expect(data).toMatchObject({ site: "amazon_jp", price: "2980", url: "https://www.amazon.co.jp/dp/B0ABCDEF12" });
  });

  it("readClipHash bỏ qua dữ liệu hỏng", () => {
    expect(readClipHash("")).toBeNull();
    expect(readClipHash("#%E0%A4%A")).toBeNull();
    expect(readClipHash("#" + encodeURIComponent("[1,2]"))).toBeNull();
    expect(readClipHash("#" + encodeURIComponent('{"title":"a"}'))).toEqual({ title: "a" });
  });
});
