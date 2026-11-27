"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

/**
 * Một lựa chọn trên màn desk (tab tầng 2, chip tầng 3, kỳ/tuần…) giữ trong query của URL, đổi bằng `router.replace`
 * (không thêm bước vào lịch sử) để quay lại/tải lại vẫn đúng chỗ. Giá trị bằng `fallback` thì bỏ khỏi URL.
 *
 *   const [tab, setTab] = useUrlParam("tab", "cho", ["cho", "xong"] as const);
 */
export function useUrlParam<V extends string>(name: string, fallback: V, allowed?: readonly V[]): [V, (value: V) => void] {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const raw = params.get(name);
  const fromUrl = raw !== null && (!allowed || (allowed as readonly string[]).includes(raw)) ? (raw as V) : fallback;
  // đổi ngay trên màn (router.replace cập nhật URL sau một nhịp); URL đổi rồi thì URL là nguồn
  const [local, setLocal] = useState<{ value: V; raw: string | null } | null>(null);
  const value = local && local.raw === raw ? local.value : fromUrl;
  const set = useCallback(
    (next: V) => {
      setLocal({ value: next, raw });
      const sp = new URLSearchParams(window.location.search);
      if (next === fallback) sp.delete(name);
      else sp.set(name, next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [name, fallback, pathname, router, raw],
  );
  return [value, set];
}
