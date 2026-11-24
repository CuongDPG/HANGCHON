import { PackageOpen } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { StorePlaceholder } from "@/components/store/store-placeholder";

/** Trang sản phẩm (e1, e2, e7, e8): lý do chọn, điều chưa ưng, dải số sàng lọc, đánh giá có ảnh. */
export default function ProductPage() {
  return (
    <StorePlaceholder
      title="Sản phẩm"
      backHref="/"
      icon={<PackageOpen />}
      emptyTitle="Món này chưa lên kệ"
      emptyDescription="Trang sản phẩm sẽ có ảnh thật, lý do chọn, điều chưa ưng và hồ sơ chọn đầy đủ."
      action={<ButtonLink href="/" variant="secondary">Về kệ hàng</ButtonLink>}
    />
  );
}
