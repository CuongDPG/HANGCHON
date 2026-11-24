"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./client";

/** Người đăng nhập bàn làm việc: chị (`owner`) hoặc người phụ giúp (`helper`). */
export type SessionUser = {
  id: string;
  email: string;
  name: string;
  role: "owner" | "helper" | (string & {});
};

export type LoginInput = { email: string; password: string };

export const sessionQueryKey = ["desk", "session"] as const;

export const authApi = {
  me: () => api.get<SessionUser>("/api/desk/auth/me"),
  login: (input: LoginInput) => api.post<SessionUser>("/api/desk/auth/login", input),
  logout: () => api.post<void>("/api/desk/auth/logout"),
};

export type SessionStatus = "loading" | "authenticated" | "unauthenticated" | "error";

/**
 * Phiên đăng nhập hiện tại. `unauthenticated` khi API trả 401; `error` khi không tới được máy chủ
 * hoặc máy chủ lỗi (khi đó KHÔNG chuyển sang trang đăng nhập, chỉ báo lỗi và cho thử lại).
 */
export function useSession() {
  const query = useQuery<SessionUser | null, ApiError>({
    queryKey: sessionQueryKey,
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });

  let status: SessionStatus;
  if (query.isPending) status = "loading";
  else if (query.isError) status = "error";
  else status = query.data ? "authenticated" : "unauthenticated";

  return { user: query.data ?? null, status, error: query.error, refetch: query.refetch };
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: authApi.login,
    meta: { silentError: true }, // form đăng nhập tự hiện lỗi tại chỗ
    onSuccess: (user) => qc.setQueryData(sessionQueryKey, user),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      qc.clear();
      // Tải lại hẳn trang để xoá mọi trạng thái giữ lại trong bộ nhớ (Activity của Next.js giữ trang đã ẩn),
      // đúng cách tài liệu Next.js khuyên cho đăng xuất.
      window.location.replace("/desk/dang-nhap");
    },
  });
}
