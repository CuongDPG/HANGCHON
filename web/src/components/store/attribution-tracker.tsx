"use client";

import { useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { captureAttribution } from "@/lib/attribution";

/** Nhớ `?src=` / `?ref=` khi khách mở link bài đăng hoặc link giới thiệu (đặt trong `<Suspense>`). */
export function AttributionTracker() {
  const params = useSearchParams();
  useEffect(() => {
    captureAttribution(new URLSearchParams(params.toString()));
  }, [params]);
  return null;
}
