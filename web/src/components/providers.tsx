"use client";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api/client";
import { ConfirmProvider } from "@/components/ui/confirm";
import { Toaster, notifyError } from "@/components/ui/toast";

declare module "@tanstack/react-query" {
  interface Register {
    defaultError: ApiError | Error;
    /** `silentError: true` khi màn hình tự hiện lỗi tại chỗ, không cần toast chung. */
    mutationMeta: { silentError?: boolean };
  }
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Không thử lại lỗi 4xx (thiếu quyền, không tìm thấy, dữ liệu sai); lỗi mạng/5xx thử lại 1 lần.
        retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1,
      },
    },
    // Mọi mutation lỗi đều hiện toast tiếng Việt, trừ khi đặt meta.silentError.
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        if (!mutation.meta?.silentError) notifyError(error);
      },
    }),
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <ConfirmProvider>{children}</ConfirmProvider>
      <Toaster />
    </QueryClientProvider>
  );
}
