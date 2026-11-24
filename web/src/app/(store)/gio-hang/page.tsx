import { ShoppingBag } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { StorePlaceholder } from "@/components/store/store-placeholder";

export const metadata = { title: "Giỏ hàng" };

/** Giỏ hàng (e4). */
export default function CartPage() {
  return (
    <StorePlaceholder
      title="Giỏ hàng"
      icon={<ShoppingBag />}
      emptyTitle="Giỏ đang trống"
      emptyDescription="Chọn món trên kệ hoặc trong đợt đang mở. Không cần tạo tài khoản để đặt."
      action={<ButtonLink href="/">Xem kệ hàng</ButtonLink>}
    />
  );
}
