import type { MetadataRoute } from "next";
import { connection } from "next/server";
import { siteUrl } from "@/lib/api/catalog";

/**
 * robots.txt (e10): mở cho máy tìm kiếm và trợ lý mua sắm AI; chặn bàn làm việc, giỏ, đặt hàng, link đánh giá.
 * Tính lúc có request để SITE_URL lấy từ env lúc chạy (một image dùng cho mọi tên miền), không dựng sẵn lúc build.
 */
export default async function robots(): Promise<MetadataRoute.Robots> {
  await connection();
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/desk", "/api/", "/gio-hang", "/dat-hang", "/don/", "/danh-gia/"] }],
    sitemap: siteUrl("/sitemap.xml"),
  };
}
