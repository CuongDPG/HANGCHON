/**
 * Lớp gọi API dùng chung cho Server Component và client.
 *
 * - Trình duyệt: gọi đường dẫn tương đối `/api/...` (Next.js chuyển tiếp sang FastAPI, cookie httpOnly đi kèm).
 * - Máy chủ (Server Component, route handler): gọi thẳng `API_ORIGIN`. Cần cookie đăng nhập thì dùng
 *   `serverFetch` trong `./server.ts` (tự chuyển cookie của request hiện tại).
 *
 * Lỗi luôn là `ApiError` với `message` tiếng Việt đọc được (lấy từ `detail` của API nếu có).
 */

/** Danh sách có phân trang — khớp `Paginated[T]` của backend. */
export type Paginated<T> = {
  items: T[];
  total: number;
};

export type QueryValue = string | number | boolean | null | undefined | Array<string | number>;

export type ApiRequestOptions = Omit<RequestInit, "body" | "method"> & {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** Tham số query; `null`/`undefined` bị bỏ qua, mảng thành nhiều tham số cùng tên. */
  query?: Record<string, QueryValue>;
  /** Đối tượng JS sẽ được gửi dạng JSON; `FormData` gửi nguyên dạng (tải tệp). */
  body?: unknown;
  /** Chuỗi cookie chuyển tiếp khi gọi từ máy chủ (xem `serverFetch`). */
  cookie?: string;
};

export class ApiError extends Error {
  readonly status: number;
  /** `detail` nguyên bản từ API (chuỗi, mảng lỗi kiểm tra, hoặc đối tượng). */
  readonly detail: unknown;
  /** Không tới được máy chủ (mất mạng, API chưa chạy). */
  readonly isNetwork: boolean;

  constructor(message: string, status: number, detail?: unknown, isNetwork = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.isNetwork = isNetwork;
  }

  get isUnauthorized() {
    return this.status === 401;
  }
}

const STATUS_MESSAGES: Record<number, string> = {
  400: "Yêu cầu chưa hợp lệ.",
  401: "Phiên đăng nhập đã hết. Chị đăng nhập lại nhé.",
  403: "Tài khoản này không có quyền làm việc này.",
  404: "Không tìm thấy dữ liệu.",
  409: "Dữ liệu vừa được thay đổi ở nơi khác. Tải lại rồi thử lại.",
  413: "Tệp quá lớn.",
  422: "Thông tin nhập chưa hợp lệ.",
  429: "Thao tác quá nhanh. Đợi một chút rồi thử lại.",
};

export const NETWORK_ERROR_MESSAGE = "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.";
const SERVER_ERROR_MESSAGE = "Máy chủ đang gặp sự cố. Thử lại sau ít phút.";

/** Lấy câu thông báo từ `detail` kiểu FastAPI: chuỗi, hoặc mảng lỗi kiểm tra `[{loc, msg}]`. */
function messageFromDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter((m): m is string => !!m);
    if (msgs.length) return msgs.join(" · ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const m = (detail as { message: unknown }).message;
    if (typeof m === "string" && m.trim()) return m;
  }
  return null;
}

/** Câu thông báo tiếng Việt cho mọi loại lỗi (dùng trong notifyError, khối lỗi). */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return "Đã có lỗi xảy ra. Thử lại nhé.";
}

function apiBase(): string {
  if (typeof window !== "undefined") return "";
  return (process.env.API_ORIGIN ?? "http://localhost:8010").replace(/\/$/, "");
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
    else params.append(key, String(value));
  }
  const qs = params.toString();
  return `${apiBase()}${p}${qs ? `?${qs}` : ""}`;
}

export async function apiFetch<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = "GET", query, body, cookie, headers: extraHeaders, ...init } = options;
  const headers = new Headers(extraHeaders);
  headers.set("Accept", "application/json");
  if (cookie) headers.set("Cookie", cookie);

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      ...init,
      method,
      headers,
      body: payload,
      credentials: "same-origin",
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(NETWORK_ERROR_MESSAGE, 0, undefined, true);
  }

  if (res.status === 204) return undefined as T;

  const isJson = res.headers.get("content-type")?.includes("application/json") ?? false;
  const data: unknown = isJson ? await res.json().catch(() => null) : await res.text().catch(() => null);

  if (!res.ok) {
    const detail = isJson && data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
    const fromApi = isJson ? messageFromDetail(detail) : null;
    // Next.js trả 500 dạng chữ khi không chuyển tiếp được tới API (API chưa chạy).
    const unreachable = !isJson && res.status >= 500;
    const message =
      fromApi ??
      (unreachable ? NETWORK_ERROR_MESSAGE : (STATUS_MESSAGES[res.status] ?? (res.status >= 500 ? SERVER_ERROR_MESSAGE : `Lỗi ${res.status}.`)));
    throw new ApiError(message, res.status, detail, unreachable);
  }

  return data as T;
}

/** Cú pháp gọn: `api.get<Product>("/api/store/products/abc")`, `api.post("/api/desk/x", { body })`. */
export const api = {
  get: <T>(path: string, options?: Omit<ApiRequestOptions, "method" | "body">) => apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<ApiRequestOptions, "method" | "body">) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<ApiRequestOptions, "method" | "body">) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: Omit<ApiRequestOptions, "method" | "body">) =>
    apiFetch<T>(path, { ...options, method: "PUT", body }),
  delete: <T = void>(path: string, options?: Omit<ApiRequestOptions, "method" | "body">) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};
