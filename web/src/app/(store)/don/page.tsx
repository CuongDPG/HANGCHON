import { Package } from "lucide-react";
import { StorePlaceholder } from "@/components/store/store-placeholder";

export const metadata = { title: "Tra cứu đơn" };

/** Tra cứu đơn (e5): bằng số điện thoại và mã đơn. */
export default function OrderLookupPage() {
  return (
    <StorePlaceholder
      title="Đơn của bạn"
      description="Xem hành trình đơn bằng số điện thoại và mã đơn (vd. HC-1248)."
      icon={<Package />}
      emptyTitle="Ô tra cứu đơn sắp có"
      emptyDescription="Bạn sẽ thấy từng chặng: đã nhận đơn, chốt đợt, hàng về, chị kiểm hàng, giao cho bạn."
    />
  );
}
