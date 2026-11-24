/** Manifest PWA của bàn làm việc (phạm vi /desk). Icon ở public/desk/. */
export function GET() {
  const manifest = {
    id: "/desk",
    name: "Hàng Chọn · Bàn làm việc",
    short_name: "Hàng Chọn",
    description: "Bàn làm việc của người chọn hàng: săn hàng, bàn chọn, nội dung, khách, giám sát AI.",
    lang: "vi",
    start_url: "/desk",
    scope: "/desk",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f6f2",
    theme_color: "#f6f6f2",
    icons: [
      { src: "/desk/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/desk/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/desk/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Chờ duyệt", url: "/desk/duyet" },
      { name: "Săn hàng", url: "/desk/san-hang" },
    ],
  };
  return new Response(JSON.stringify(manifest), {
    headers: { "Content-Type": "application/manifest+json; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
