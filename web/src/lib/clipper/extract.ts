/**
 * «Gửi sang Hàng Chọn» — phần đọc trang sản phẩm, chạy NGAY TRÊN TRANG SÀN trong trình duyệt của chị (bookmarklet).
 *
 * `clipPage` phải TỰ ĐỦ: không import, không gọi hàm/biến ngoài thân hàm (chỉ biến toàn cục của trình duyệt), vì
 * bookmarklet được dựng bằng `clipPage.toString()` (xem `bookmarklet.ts`). `extract.test.ts` chạy lại bản chuỗi trong
 * phạm vi trống để giữ điều này. Không dùng cú pháp cần hàm phụ của trình biên dịch (class, async, generator).
 *
 * Mỗi sàn một bộ đọc, dựa vào tín hiệu bền: thẻ meta og:*, JSON-LD Product, JSON nhúng trong <script>
 * (window.__INIT_DATA, skuProps…), phần tử có id/class ổn định (#productTitle, #landingImage…). Ảnh đổi sang cỡ gốc
 * (bỏ đuôi `_400x400.jpg`, `._AC_SX300_`, `?_ex=128x128`). Không đọc được trường nào thì để trống, không đoán.
 */

export type ClipPayload = {
  url: string;
  site: string;
  title: string;
  price: string | null;
  currency: string | null;
  images: string[];
  description: string | null;
  specs: Record<string, string>;
  variants: string[];
  seller_name: string | null;
  seller_url: string | null;
  rating: number | null;
  review_count: number | null;
  sales_count: number | null;
  moq: number | null;
};

export function clipPage(doc: Document, href: string): ClipPayload {
  const host = new URL(href).hostname.toLowerCase();
  const on = (d: string) => host === d || host.endsWith("." + d);
  const clean = (s: string | null | undefined) => (s || "").replace(/\s+/g, " ").trim();
  const all = (sel: string): Element[] => {
    try {
      return Array.prototype.slice.call(doc.querySelectorAll(sel));
    } catch {
      return [];
    }
  };
  const one = (sel: string): Element | null => all(sel)[0] || null;
  const text = (...sels: string[]) => {
    for (const s of sels) {
      for (const el of all(s)) {
        const t = clean(el.textContent);
        if (t) return t;
      }
    }
    return "";
  };
  const attr = (sel: string, name: string) => clean(one(sel)?.getAttribute(name));
  const meta = (...names: string[]) => {
    for (const n of names) {
      const v = attr(`meta[property="${n}"]`, "content") || attr(`meta[name="${n}"]`, "content") || attr(`meta[itemprop="${n}"]`, "content");
      if (v) return v;
    }
    return "";
  };
  const abs = (u: string | null | undefined) => {
    const s = clean(u);
    if (!s || s.startsWith("data:")) return "";
    try {
      const x = new URL(s, href);
      if (x.protocol === "http:") x.protocol = "https:";
      return x.protocol === "https:" ? x.href : "";
    } catch {
      return "";
    }
  };
  // ảnh cỡ gốc: alicdn `….jpg_400x400q90.jpg_.webp` → `….jpg`; Amazon `…._AC_SX300_.jpg` → `….jpg`; Rakuten thumbnail
  const big = (u: string) =>
    u
      .replace(/(\.(?:jpe?g|png|webp|gif))_[^/]*$/i, "$1")
      .replace(/\._[A-Za-z0-9_,+-]+_\.(jpe?g|png|gif|webp)$/i, ".$1")
      .replace(/^https:\/\/thumbnail\.image\.rakuten\.co\.jp\/@0_mall\//, "https://image.rakuten.co.jp/")
      .replace(/\?_ex=\d+x\d+$/, "")
      .replace(/^(https:\/\/[a-z]+\.r10s\.jp\/[^?]+)\?fitin=[\d:]+$/, "$1");
  const num = (s: string | null | undefined): number | null => {
    const t = clean(s).replace(/[,，]/g, "");
    const m = t.match(/(\d+(?:\.\d+)?)\s*(万|千|[kK]\b)?/);
    if (!m) return null;
    const n = parseFloat(m[1]) * (m[2] === "万" ? 10000 : m[2] === "千" || /k/i.test(m[2] || "") ? 1000 : 1);
    return isFinite(n) ? n : null;
  };
  const int = (s: string | null | undefined) => {
    const n = num(s);
    return n === null ? null : Math.round(n);
  };

  // văn bản các thẻ <script> (JSON nhúng), bỏ thoát `\/` và `/`
  let scripts = "";
  for (const s of all("script")) {
    if (scripts.length > 4_000_000) break;
    const t = s.textContent || "";
    if (t.length > 20) scripts += "\n" + t;
  }
  scripts = scripts.replace(/\\u002F/gi, "/").replace(/\\\//g, "/");
  const sre = (re: RegExp) => {
    const m = scripts.match(re);
    return m ? m[1] : "";
  };
  // JSON ngay sau `"key":` trong script (mảng hoặc đối tượng, đếm ngoặc) → giá trị; lỗi → null
  const jsonAfter = (key: string): unknown => {
    let from = 0;
    for (let tries = 0; tries < 5; tries++) {
      const i = scripts.indexOf(`"${key}"`, from);
      if (i < 0) return null;
      from = i + key.length + 2;
      let j = from;
      while (j < scripts.length && /[\s:]/.test(scripts[j])) j++;
      const open = scripts[j];
      if (open !== "[" && open !== "{") continue;
      const close = open === "[" ? "]" : "}";
      let depth = 0;
      let inStr = false;
      for (let k = j; k < scripts.length && k < j + 400_000; k++) {
        const ch = scripts[k];
        if (inStr) {
          if (ch === "\\") k++;
          else if (ch === '"') inStr = false;
        } else if (ch === '"') inStr = true;
        else if (ch === open) depth++;
        else if (ch === close && --depth === 0) {
          try {
            return JSON.parse(scripts.slice(j, k + 1));
          } catch {
            break;
          }
        }
      }
    }
    return null;
  };

  const out: ClipPayload = {
    url: href,
    site: "web",
    title: "",
    price: null,
    currency: null,
    images: [],
    description: null,
    specs: {},
    variants: [],
    seller_name: null,
    seller_url: null,
    rating: null,
    review_count: null,
    sales_count: null,
    moq: null,
  };
  const imgs: string[] = [];
  const addImg = (u: string | null | undefined) => {
    const a = abs(u);
    if (a && !/\.svg(\?|$)|sprite|icon|logo|placeholder|blank\.gif|transparent/i.test(a)) imgs.push(big(a));
  };
  const imgsOf = (sel: string) => {
    for (const el of all(sel)) {
      addImg(el.getAttribute("data-old-hires") || el.getAttribute("data-src") || el.getAttribute("data-lazy-src") || el.getAttribute("data-ks-lazyload") || el.getAttribute("src"));
    }
  };
  const setSpec = (k: string, v: string) => {
    k = clean(k).replace(/[:：]\s*$/, "").slice(0, 120);
    v = clean(v).slice(0, 500);
    if (k && v && k !== v && Object.keys(out.specs).length < 40 && !(k in out.specs)) out.specs[k] = v;
  };
  const specsFrom = (rowSel: string, keySel: string, valSel: string) => {
    for (const row of all(rowSel)) {
      const k = row.querySelector(keySel);
      const v = row.querySelector(valSel);
      if (k && v) setSpec(k.textContent || "", v.textContent || "");
    }
  };
  const specsFromLines = (sel: string) => {
    for (const el of all(sel)) {
      const m = clean(el.textContent).match(/^([^:：]{1,60})[:：]\s*(.+)$/);
      if (m) setSpec(m[1], m[2]);
    }
  };
  const setPrice = (s: string | null | undefined) => {
    if (out.price) return;
    const n = num(s);
    if (n !== null && n > 0) out.price = String(n);
  };
  const currencyOf = (s: string) =>
    /US\$|\$/.test(s) && !/[¥￥]/.test(s) ? "USD" : /€/.test(s) ? "EUR" : /₫|VND|đ\b/i.test(s) ? "VND" : /[¥￥円]/.test(s) ? (on("jp") || host.endsWith(".jp") ? "JPY" : "CNY") : "";

  // ---- chung: JSON-LD Product + og:* (mọi trang) ------------------------------------------------------------------
  const products: Record<string, unknown>[] = [];
  const walk = (x: unknown) => {
    if (!x || typeof x !== "object") return;
    if (Array.isArray(x)) return x.forEach(walk);
    const o = x as Record<string, unknown>;
    const t = o["@type"];
    if (t === "Product" || (Array.isArray(t) && t.indexOf("Product") >= 0)) products.push(o);
    if (o["@graph"]) walk(o["@graph"]);
  };
  for (const s of all('script[type="application/ld+json"]')) {
    try {
      walk(JSON.parse(s.textContent || ""));
    } catch {
      /* JSON-LD hỏng: bỏ qua */
    }
  }
  const ld = products[0] || null;
  const ldVal = (o: unknown, k: string): unknown => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined);
  const str = (v: unknown) => (typeof v === "string" || typeof v === "number" ? clean(String(v)) : "");
  let ldTitle = "";
  if (ld) {
    ldTitle = str(ld.name);
    const im = ld.image;
    for (const u of Array.isArray(im) ? im : [im]) addImg(typeof u === "string" ? u : str(ldVal(u, "url")));
    let offer = ld.offers;
    if (Array.isArray(offer)) offer = offer[0];
    const p = str(ldVal(offer, "price")) || str(ldVal(offer, "lowPrice"));
    if (p) {
      setPrice(p);
      out.currency = str(ldVal(offer, "priceCurrency")).toUpperCase() || null;
    }
    const ar = ld.aggregateRating;
    out.rating = num(str(ldVal(ar, "ratingValue")));
    out.review_count = int(str(ldVal(ar, "reviewCount")) || str(ldVal(ar, "ratingCount")));
    const seller = ldVal(offer, "seller") || ld.brand;
    out.seller_name = str(ldVal(seller, "name")) || (typeof seller === "string" ? clean(seller) : "") || null;
    const d = str(ld.description);
    if (d) out.description = d;
  }
  const ogTitle = meta("og:title", "twitter:title");
  const ogImages: string[] = [];
  for (const el of all('meta[property="og:image"], meta[name="og:image"], meta[property="og:image:url"], meta[name="twitter:image"]')) ogImages.push(el.getAttribute("content") || "");
  setPrice(meta("product:price:amount", "og:price:amount", "price"));
  if (out.price && !out.currency) out.currency = meta("product:price:currency", "og:price:currency", "priceCurrency").toUpperCase() || null;

  // ---- từng sàn ----------------------------------------------------------------------------------------------------
  let title = "";
  let priceText = "";
  if (on("1688.com")) {
    out.site = "1688";
    out.currency = "CNY";
    title = text(".title-content h1", ".title-text", "[class*=title-content] h1", ".d-title", ".mod-detail-title h1") || sre(/"subject"\s*:\s*"([^"]{4,300})"/);
    priceText = text(".price-content .price-text", "[class*=price-text]", ".price-now", ".price .value", "[class*=price-info] [class*=price]") || sre(/"(?:showPrice|price|minPrice|priceDisplay)"\s*:\s*"?(\d+(?:\.\d+)?)/);
    imgsOf(".detail-gallery-turn img, .detail-gallery-img, [class*=gallery] img, .img-list-wrapper img, .tab-trigger img, .vertical-img img");
    const list = jsonAfter("offerImgList") || jsonAfter("imageList") || jsonAfter("images");
    if (Array.isArray(list)) for (const u of list) addImg(typeof u === "string" ? u : str(ldVal(u, "fullPathImageURI")) || str(ldVal(u, "imageURI")) || str(ldVal(u, "url")));
    for (const m of scripts.match(/https?:\/\/cbu01\.alicdn\.com\/img\/ibank\/[^"'\s\\)]+?\.(?:jpe?g|png|webp)/gi) || []) addImg(m);
    imgsOf('img[src*="cbu01.alicdn.com/img/ibank"]');
    const attrs = jsonAfter("featureAttributes") || jsonAfter("productFeatureList") || jsonAfter("attributes");
    if (Array.isArray(attrs)) for (const a of attrs) setSpec(str(ldVal(a, "name")) || str(ldVal(a, "attributeName")), str(ldVal(a, "value")) || (Array.isArray(ldVal(a, "values")) ? (ldVal(a, "values") as unknown[]).map(str).join(", ") : ""));
    specsFrom(".offer-attr-item, [class*=attr-item]", ".offer-attr-item-name, [class*=attr-name], [class*=item-name]", ".offer-attr-item-value, [class*=attr-value], [class*=item-value]");
    specsFrom(".obj-content tr, .od-pc-attribute tr, [class*=attribute] tr", "th, td:nth-child(1)", "td:last-child");
    const sku = jsonAfter("skuProps");
    if (Array.isArray(sku)) for (const p of sku) for (const v of (ldVal(p, "value") as unknown[]) || []) out.variants.push(str(ldVal(p, "prop")) ? `${str(ldVal(p, "prop"))}: ${str(ldVal(v, "name"))}` : str(ldVal(v, "name")));
    out.seller_name = text(".company-name", "[class*=company-name]", ".shop-company-name") || sre(/"(?:companyName|sellerLoginId|loginId)"\s*:\s*"([^"]{2,120})"/) || out.seller_name;
    out.seller_url = abs(attr('a[href*=".1688.com"][class*=company], a[class*=company-name], .shop-company-name a', "href")) || abs(sre(/"(?:winportUrl|shopUrl)"\s*:\s*"([^"]+)"/)) || null;
    out.sales_count = int(sre(/"(?:saleNum|saledCount|soldOut|bookedCount)"\s*:\s*"?(\d+)/)) ?? int(text("[class*=sale-count]", "[class*=sold]"));
    out.moq = int(sre(/"(?:beginAmount|minOrderQuantity|quantityBegin)"\s*:\s*"?(\d+)/));
    out.rating = num(sre(/"(?:rateAverageStarLevel|compositeServiceScore)"\s*:\s*"?(\d(?:\.\d+)?)/)) ?? out.rating;
  } else if (on("taobao.com") || on("tmall.com") || on("tmall.hk")) {
    out.site = on("taobao.com") ? "taobao" : "tmall";
    out.currency = "CNY";
    title = text("[class*=mainTitle]", "[class*=ItemTitle] h1", ".tb-main-title", ".tb-detail-hd h1", "h1") || sre(/"title"\s*:\s*"([^"]{4,300})"/);
    priceText = text("[class*=highlightPrice] [class*=priceText]", "[class*=priceText]", ".tm-promo-price .tm-price", ".tm-price", "#J_StrPrice .tb-rmb-num", "#J_PromoPriceNum");
    imgsOf("[class*=thumbnail] img, [class*=picGallery] img, [class*=mainPic] img, #J_UlThumb img, #J_ImgBooth");
    const list = jsonAfter("images") || jsonAfter("auctionImages");
    if (Array.isArray(list)) for (const u of list) addImg(typeof u === "string" ? u : "");
    for (const m of scripts.match(/(?:https?:)?\/\/(?:img|gw|gd\d)\.alicdn\.com\/(?:imgextra|bao\/uploaded)\/[^"'\s\\)]+?\.(?:jpe?g|png|webp)/gi) || []) addImg(m);
    specsFrom("[class*=generalParamsInfoItem], [class*=paramsInfoItem]", "[class*=Title], [class*=title]", "[class*=SubTitle], [class*=subtitle], [class*=Value]");
    specsFromLines("#J_AttrUL li, .attributes-list li, [class*=Attrs] li");
    for (const el of all("[class*=skuItem] [class*=valueItem], [class*=SkuContent--valueItem], #J_DetailMeta .tb-sku li[title], .J_TSaleProp li[title]")) {
      const t = clean(el.getAttribute("title")) || clean(el.textContent);
      if (t) out.variants.push(t);
    }
    out.seller_name = text("[class*=shopName]", "[class*=ShopHeader] [class*=name]", ".tb-shop-name", ".slogo-shopname", ".shop-name") || out.seller_name;
    out.seller_url = abs(attr("[class*=shopName] a, a[class*=shopName], .tb-shop-name a, a.slogo-shopname", "href")) || abs(attr('a[href*="shop"][href*=".taobao.com"], a[href*=".tmall.com"][href*="shop"]', "href")) || null;
    out.sales_count = int(text("[class*=salesDesc]", "[class*=sales]", "#J_SellCounter", ".tm-ind-sellCount .tm-count"));
    out.review_count = int(text("#J_RateCounter", ".tm-ind-reviewCount .tm-count", "[class*=rateCount]")) ?? out.review_count;
  } else if (on("amazon.co.jp") || on("amazon.com")) {
    out.site = on("amazon.co.jp") ? "amazon_jp" : "amazon";
    out.currency = on("amazon.co.jp") ? "JPY" : "USD";
    title = text("#productTitle", "#title");
    priceText = text("#corePriceDisplay_desktop_feature_div .a-price .a-offscreen", "#corePrice_feature_div .a-price .a-offscreen", "#corePrice_desktop .a-offscreen", "#apex_desktop .a-price .a-offscreen", "#priceblock_ourprice", "#priceblock_dealprice", ".a-price .a-offscreen") || text(".a-price-whole");
    const dyn = attr("#landingImage", "data-a-dynamic-image") || attr("#imgBlkFront", "data-a-dynamic-image");
    if (dyn) {
      try {
        Object.keys(JSON.parse(dyn)).forEach(addImg);
      } catch {
        /* thuộc tính hỏng */
      }
    }
    for (const m of scripts.match(/"hiRes"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/I\/[^"]+)"/g) || []) addImg(m.replace(/^"hiRes"\s*:\s*"|"$/g, ""));
    for (const m of scripts.match(/"large"\s*:\s*"(https:\/\/m\.media-amazon\.com\/images\/I\/[^"]+)"/g) || []) addImg(m.replace(/^"large"\s*:\s*"|"$/g, ""));
    imgsOf("#landingImage, #altImages img, #imageBlock img");
    out.rating = num((attr("#acrPopover", "title") || text("#acrPopover .a-icon-alt", "[data-hook=rating-out-of-text]")).replace(/^.*うち\s*/, "")) ?? out.rating;
    out.review_count = int(text("#acrCustomerReviewText", "[data-hook=total-review-count]")) ?? out.review_count;
    out.sales_count = int(text("#social-proofing-faceout-title-tk_bought", "[id*=social-proofing] .a-text-bold"));
    out.seller_name = text("#sellerProfileTriggerId", "#merchantInfoFeature_feature_div .offer-display-feature-text-message", "#bylineInfo") || out.seller_name;
    out.seller_url = abs(attr("#sellerProfileTriggerId", "href") || attr("#bylineInfo", "href")) || null;
    specsFrom("#productOverview_feature_div tr, #poExpander tr", "td:nth-child(1)", "td:nth-child(2)");
    specsFrom("#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr, #technicalSpecifications_section_1 tr", "th", "td");
    for (const li of all("#detailBullets_feature_div li")) {
      const spans = li.querySelectorAll(".a-list-item > span");
      if (spans.length >= 2) setSpec(clean(spans[0].textContent).replace(/[‎‏:：]/g, ""), spans[1].textContent || "");
    }
    const bullets = all("#feature-bullets li").map((li) => clean(li.textContent)).filter(Boolean);
    if (bullets.length) out.description = bullets.join("\n");
    for (const el of all("#twister li[title], #variation_color_name li img[alt], #variation_size_name option, #inline-twister-expander-content-color_name li img[alt]")) {
      const t = clean(el.getAttribute("title") || el.getAttribute("alt") || el.textContent).replace(/^(クリックして|Click to select)\s*/, "");
      if (t && !/^選択|^Select/.test(t)) out.variants.push(t);
    }
  } else if (on("rakuten.co.jp")) {
    out.site = "rakuten";
    out.currency = "JPY";
    title = text(".item_name", "[class*=item-name]", "h1", ".normal_reserve_item_name");
    priceText = attr("#priceCalculationConfig", "data-price") || text("[class*=price--]", ".price2", "#priceCalculationConfig", ".important[class*=price]", "[class*=value--] [class*=number]");
    imgsOf('[class*=image-gallery] img, [class*=thumbnail] img, img[src*="image.rakuten.co.jp"], img[src*="tshop.r10s.jp"], img[src*="shop.r10s.jp"]');
    for (const el of all('a[href*="image.rakuten.co.jp"]')) addImg(el.getAttribute("href"));
    const shop = new URL(href).pathname.split("/").filter(Boolean)[0] || "";
    out.seller_name = text("[class*=shop-name]", ".shop_name", "[class*=shopName]") || meta("og:site_name") || shop || out.seller_name;
    out.seller_url = shop ? `https://www.rakuten.co.jp/${shop}/` : null;
    out.review_count = int(text("[class*=review-count]", "[class*=reviewCount]", ".revRvwUserEntryCnt")) ?? out.review_count;
    out.rating = num(text("[class*=review-score]", "[class*=reviewScore]", ".revEvaNumber")) ?? out.rating;
    specsFrom("table[class*=spec] tr, .item-spec tr, [class*=specTable] tr", "th", "td");
  }

  // ---- ghép + dự phòng ---------------------------------------------------------------------------------------------
  out.title = (title || ldTitle || ogTitle || clean(doc.title).replace(/\s*[-|｜–]\s*(淘宝网|天猫.*|阿里巴巴|1688\.com|Amazon\.co\.jp.*|楽天市場.*|Amazon\.com.*)$/, "")).slice(0, 300);
  if (priceText) {
    const c = currencyOf(priceText);
    const n = num(priceText);
    if (n !== null && n > 0) {
      out.price = String(n);
      if (c && out.site === "web") out.currency = c;
    }
  }
  if (out.price && !out.currency) out.currency = currencyOf(text("[itemprop=price]", "[class*=price]")) || null;
  if (!out.price) out.currency = null;
  ogImages.forEach(addImg);
  if (out.site === "web" && imgs.length < 3) {
    // trang lạ: thêm các ảnh to nhất đang hiện (≥ 200×200)
    const sized = all("img")
      .map((el) => {
        const im = el as HTMLImageElement;
        return { u: im.currentSrc || im.getAttribute("src") || "", a: (im.naturalWidth || im.width || 0) * (im.naturalHeight || im.height || 0) };
      })
      .filter((x) => x.a >= 40_000)
      .sort((x, y) => y.a - x.a);
    sized.slice(0, 12).forEach((x) => addImg(x.u));
  }
  if (!out.description) out.description = meta("og:description", "description") || null;
  if (out.description) out.description = out.description.slice(0, 4000);
  out.images = imgs.filter((u, i) => imgs.indexOf(u) === i && u.length <= 1000).slice(0, 20);
  out.variants = out.variants.map((v) => clean(v).slice(0, 200)).filter((v, i, a) => v && a.indexOf(v) === i).slice(0, 40);
  if (out.seller_name) out.seller_name = out.seller_name.slice(0, 200);
  if (out.rating !== null && (out.rating < 0 || out.rating > 5)) out.rating = null;
  return out;
}
