/**
 * Header bảo mật cho mọi trang web (website + bàn làm việc). Dùng trong next.config.ts.
 * Không đặt cho /api/*: API tự trả header của mình (tệp tải lên có CSP sandbox riêng).
 */
export const SECURITY_HEADERS: { key: string; value: string }[] = [
  // không cho trang khác nhúng bàn làm việc vào khung (clickjacking: lừa chị bấm «Duyệt»)
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // link ra ngoài không mang theo đường dẫn có mã xem đơn (?t=...) hay mã đánh giá
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // máy ảnh / micro: bàn làm việc chụp ảnh, ghi âm ghi chú thử hàng
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

/** Mọi đường dẫn trừ /api/* (rewrite sang FastAPI). */
export const SECURITY_HEADERS_SOURCE = "/((?!api/).*)";
