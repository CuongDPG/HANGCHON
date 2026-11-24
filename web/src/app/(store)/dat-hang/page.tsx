import { Suspense } from "react";
import { CheckoutScreen } from "@/components/orders/checkout-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Đặt hàng" };

/** Đặt hàng một trang (e4). Đọc ?dot= (đợt) nên đặt trong <Suspense>. */
export default function CheckoutPage() {
  return (
    <Suspense fallback={<SkeletonList rows={3} />}>
      <CheckoutScreen />
    </Suspense>
  );
}
