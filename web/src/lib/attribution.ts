/**
 * Nguồn dẫn khách tới (f7, h7): `?src=<mã bài>` trong link bài đăng và `?ref=<mã giới thiệu>`.
 * Lưu ở trình duyệt (lần chạm cuối, giữ 7 ngày) để đi qua giỏ hàng tới lúc đặt; đơn gửi kèm `src` / `referral_code`.
 */

const KEY = "hc_attribution_v1";
const TTL_MS = 7 * 24 * 3600 * 1000;

export type Attribution = { src?: string; ref?: string; at: number };

function clean(v: string | null | undefined, max: number): string | undefined {
  const s = (v ?? "").trim().replace(/[^A-Za-z0-9_-]/g, "").slice(0, max);
  return s || undefined;
}

export function readAttribution(now = Date.now()): Attribution | null {
  if (typeof window === "undefined") return null;
  try {
    const data = JSON.parse(window.localStorage.getItem(KEY) ?? "null") as Attribution | null;
    if (!data || typeof data.at !== "number" || now - data.at > TTL_MS) return null;
    return data;
  } catch {
    return null;
  }
}

/** Ghi nhận tham số trên URL (nếu có). Không có tham số thì giữ nguyên nguồn cũ. */
export function captureAttribution(params: URLSearchParams, now = Date.now()) {
  const src = clean(params.get("src"), 40);
  const ref = clean(params.get("ref"), 30);
  if (!src && !ref) return;
  const prev = readAttribution(now);
  const next: Attribution = { src: src ?? prev?.src, ref: ref ?? prev?.ref, at: now };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* chế độ riêng tư: bỏ qua */
  }
}

/** Trường gửi kèm đơn. */
export function attributionFields(): { src?: string; referral_code?: string } {
  const a = readAttribution();
  return { ...(a?.src ? { src: a.src } : {}), ...(a?.ref ? { referral_code: a.ref.toUpperCase() } : {}) };
}
