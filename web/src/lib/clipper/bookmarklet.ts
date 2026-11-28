import { clipPage } from "./extract";

/**
 * Nút «Gửi sang Hàng Chọn» (bookmarklet) — chạy trên trang sàn chị đang mở (đã đăng nhập sàn):
 * 1. `clipPage` đọc trang ngay trong trình duyệt (mã nằm sẵn trong nút, KHÔNG tải script từ ngoài — CSP của sàn hay
 *    chặn script lạ, còn bookmarklet thì trình duyệt cho chạy);
 * 2. mở cửa sổ nhỏ `<bàn làm việc>/desk/kep#<JSON>`: dữ liệu đi trong phần `#` của link, không qua máy chủ nào
 *    trước khi chị bấm lưu, và không phụ thuộc `window.opener` (sàn đặt Cross-Origin-Opener-Policy thì postMessage
 *    giữa hai cửa sổ bị cắt);
 * 3. cửa sổ đó cùng origin với bàn làm việc nên dùng phiên đăng nhập sẵn có (cookie SameSite) để gọi API.
 */
export const CLIP_WINDOW = "hangchon_kep";
export const CLIP_PATH = "/desk/kep";

export function bookmarkletSource(origin: string): string {
  return (
    `(function(){var o=${JSON.stringify(origin)},d;` +
    `try{d=(${clipPage.toString()})(document,location.href)}catch(e){d={url:location.href,error:String(e&&e.message||e)}}` +
    `var u=o+${JSON.stringify(CLIP_PATH)}+"#"+encodeURIComponent(JSON.stringify(d));` +
    `if(!window.open(u,${JSON.stringify(CLIP_WINDOW)},"popup,width=560,height=860"))window.open(u,"_blank")})()`
  );
}

/** `href` của nút kéo lên thanh dấu trang. React chặn `javascript:` trong JSX → gán bằng `setAttribute`. */
export function bookmarkletHref(origin: string): string {
  return "javascript:" + encodeURIComponent(bookmarkletSource(origin));
}

/** Đọc dữ liệu cửa sổ /desk/kep nhận được ở phần `#` (null nếu không có / hỏng). */
export function readClipHash(hash: string): Record<string, unknown> | null {
  const raw = hash.replace(/^#/, "");
  if (!raw) return null;
  try {
    const v: unknown = JSON.parse(decodeURIComponent(raw));
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}
