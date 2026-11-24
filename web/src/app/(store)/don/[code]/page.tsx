import { Suspense } from "react";
import { TrackingScreen } from "@/components/orders/tracking-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Theo dõi đơn", robots: { index: false } };

/** Theo dõi một đơn (e5, g5). Đọc mã đơn + ?t= (dữ liệu theo request) nên đặt trong <Suspense>. */
export default function OrderTrackingPage() {
  return (
    <Suspense fallback={<SkeletonList rows={3} />}>
      <TrackingScreen />
    </Suspense>
  );
}
