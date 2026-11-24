import type { MetadataRoute } from "next";
import { connection } from "next/server";
import { catalogApi, siteUrl } from "@/lib/api/catalog";

/** sitemap.xml (e10): trang cố định + mọi món đang trên kệ + các đợt. Tính lúc có request (dữ liệu đổi thường xuyên). */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  await connection();
  const fixed: MetadataRoute.Sitemap = ["/", "/dot", "/nho-tim", "/ve-nguoi-chon", "/hoi"].map((path, i) => ({
    url: siteUrl(path),
    changeFrequency: "daily",
    priority: i === 0 ? 1 : 0.6,
  }));
  try {
    const rows = await catalogApi.sitemap();
    return [
      ...fixed,
      ...rows.map((r) => ({
        url: siteUrl(r.path),
        lastModified: r.lastmod ?? undefined,
        changeFrequency: "weekly" as const,
        priority: r.priority,
      })),
    ];
  } catch {
    return fixed; // API tạm lỗi vẫn trả sơ đồ tối thiểu
  }
}
