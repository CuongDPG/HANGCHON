import type { NextConfig } from "next";

import { SECURITY_HEADERS, SECURITY_HEADERS_SOURCE } from "./src/lib/security-headers";

// Web gọi API qua cùng origin: /api/* được chuyển tiếp sang FastAPI (cookie httpOnly đi kèm).
// Lưu ý: rewrites được tính lúc `next build`, nên API_ORIGIN phải có sẵn khi build bản chạy thật.
const API_ORIGIN = (process.env.API_ORIGIN ?? "http://localhost:8010").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Bản chạy thật chạy `server.js` của bản standalone bằng Node (web/Dockerfile).
  output: "standalone",
  // scripts/e2e.sh chạy `next dev` riêng trong `.next-e2e` để không đụng máy chủ dev (`.next`) của cùng bản làm việc
  distDir: process.env.NEXT_DIST_DIR || ".next",
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: SECURITY_HEADERS_SOURCE, headers: SECURITY_HEADERS }];
  },
  async redirects() {
    // Hồ sơ chọn không còn là trang công khai (chỉ ở desk, «Sản phẩm» → «Hồ sơ chọn»): link cũ về trang sản phẩm.
    // Giỏ hàng và tra cứu đơn gộp vào «Của tôi» (27/11); link theo dõi đơn `/don/[code]` giữ nguyên.
    return [
      { source: "/san-pham/:slug/ho-so-chon", destination: "/san-pham/:slug", permanent: true },
      { source: "/gio-hang", destination: "/cua-toi", permanent: true },
      { source: "/don", destination: "/cua-toi?tab=don", permanent: true },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
