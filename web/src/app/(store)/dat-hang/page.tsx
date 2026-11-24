import { CreditCard } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { StorePlaceholder } from "@/components/store/store-placeholder";

export const metadata = { title: "Đặt hàng" };

/** Đặt hàng một trang (e4): không cần tài khoản; chuyển khoản QR tự xác nhận hoặc trả khi nhận. */
export default function CheckoutPage() {
  return (
    <StorePlaceholder
      title="Đặt hàng"
      backHref="/gio-hang"
      icon={<CreditCard />}
      emptyTitle="Chưa có món nào để đặt"
      emptyDescription="Trang đặt hàng chỉ cần số điện thoại, họ tên và địa chỉ. Thanh toán bằng mã QR hoặc khi nhận hàng."
      action={<ButtonLink href="/gio-hang" variant="secondary">Về giỏ hàng</ButtonLink>}
    />
  );
}
