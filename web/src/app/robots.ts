import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/api/catalog";

/** robots.txt (e10): mở cho máy tìm kiếm và trợ lý mua sắm AI; chặn bàn làm việc, giỏ, đặt hàng, link đánh giá. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/desk", "/api/", "/gio-hang", "/dat-hang", "/don/", "/danh-gia/"] }],
    sitemap: siteUrl("/sitemap.xml"),
  };
}
