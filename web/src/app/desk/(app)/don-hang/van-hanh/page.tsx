import { Suspense } from "react";
import { OperationsScreen } from "@/components/orders/operations-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { ORDER_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Vận hành đơn hàng" };

export default function DeskOrderOpsPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={ORDER_SECTIONS} active="tien" />}>
      <OperationsScreen />
    </Suspense>
  );
}
