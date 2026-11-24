import { Suspense } from "react";
import { OperationsScreen } from "@/components/orders/operations-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Vận hành đơn hàng" };

export default function DeskOrderOpsPage() {
  return (
    <Suspense fallback={<SkeletonList rows={3} />}>
      <OperationsScreen />
    </Suspense>
  );
}
