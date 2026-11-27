import type { Metadata } from "next";
import { Suspense } from "react";
import { MyScreen } from "@/components/orders/my-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata: Metadata = {
  title: "Của tôi",
  description: "Giỏ hàng và đơn của bạn ở Hàng Chọn.",
  robots: { index: false, follow: false },
};

/** «Của tôi» (e4, e5): giỏ hàng + đơn của tôi. `/gio-hang` và `/don` chuyển hẳn về đây (next.config.ts). */
export default function MyPage() {
  return (
    <Suspense fallback={<SkeletonList rows={3} />}>
      <MyScreen />
    </Suspense>
  );
}
