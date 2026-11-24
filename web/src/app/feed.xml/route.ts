import { connection } from "next/server";

/** Nguồn cấp sản phẩm định dạng Google Merchant (e10). API dựng XML; ở đây chỉ chuyển tiếp, không cache lâu. */
export async function GET() {
  await connection();
  const origin = (process.env.API_ORIGIN ?? "http://localhost:8010").replace(/\/$/, "");
  try {
    const res = await fetch(`${origin}/api/store/catalog/feed.xml`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    return new Response(await res.text(), {
      headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=900" },
    });
  } catch {
    return new Response("<?xml version=\"1.0\" encoding=\"UTF-8\"?><error>Nguồn cấp tạm thời chưa sẵn sàng</error>", {
      status: 503,
      headers: { "Content-Type": "application/xml; charset=utf-8", "Retry-After": "300" },
    });
  }
}
