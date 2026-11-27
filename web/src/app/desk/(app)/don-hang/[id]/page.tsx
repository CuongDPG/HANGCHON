import { Suspense } from "react";
import { OrderDetailScreen } from "@/components/orders/order-detail-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Chi tiết đơn" };

export default function DeskOrderDetailPage() {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/don-hang" />}>
      <OrderDetailScreen />
    </Suspense>
  );
}
