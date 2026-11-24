import "server-only";

import { cookies } from "next/headers";
import { apiFetch, type ApiRequestOptions } from "./client";

/**
 * Gọi API từ Server Component kèm cookie của người đang xem (dùng cho trang cần đăng nhập).
 * Với cacheComponents, component gọi hàm này phải nằm trong <Suspense> (vì đọc cookies()).
 * Trang công khai của khách không cần cookie: gọi thẳng `api.get(...)` từ `./client`.
 */
export async function serverFetch<T>(path: string, options: Omit<ApiRequestOptions, "cookie"> = {}): Promise<T> {
  const cookie = (await cookies()).toString();
  return apiFetch<T>(path, { ...options, cookie: cookie || undefined });
}
