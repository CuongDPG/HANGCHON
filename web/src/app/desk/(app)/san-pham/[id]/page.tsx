import { Suspense } from "react";
import { ProductScreen } from "@/components/catalog/desk/product-screen";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Sản phẩm" };

/** Một sản phẩm, theo dõi hai chiều: Hồ sơ chọn (ngược về quá trình chọn) · Hồ sơ bán (xuôi theo đường bán) · Giá và cách bán. */
export default function DeskProductPage({ params }: PageProps<"/desk/san-pham/[id]">) {
  return (
    <Suspense fallback={<SkeletonList rows={6} />}>
      <Screen params={params} />
    </Suspense>
  );
}

async function Screen({ params }: { params: PageProps<"/desk/san-pham/[id]">["params"] }) {
  const { id } = await params;
  return <ProductScreen id={id} />;
}
