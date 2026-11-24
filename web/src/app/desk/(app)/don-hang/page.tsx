import { Suspense } from "react";
import { OrdersScreen } from "@/components/orders/orders-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Đơn hàng" };

export default function DeskOrdersPage() {
  return (
    <Suspense fallback={<SkeletonList rows={4} />}>
      <OrdersScreen />
    </Suspense>
  );
}
