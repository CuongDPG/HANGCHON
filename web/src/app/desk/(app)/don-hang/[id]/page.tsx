import { Suspense } from "react";
import { OrderDetailScreen } from "@/components/orders/order-detail-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Chi tiết đơn" };

export default function DeskOrderDetailPage() {
  return (
    <Suspense fallback={<SkeletonList rows={3} />}>
      <OrderDetailScreen />
    </Suspense>
  );
}
