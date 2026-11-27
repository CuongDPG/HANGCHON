import { Suspense } from "react";
import { OrdersScreen } from "@/components/orders/orders-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { ORDER_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Đơn hàng" };

export default function DeskOrdersPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={ORDER_SECTIONS} active="orders" rows={4} />}>
      <OrdersScreen />
    </Suspense>
  );
}
