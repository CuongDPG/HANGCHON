import { Suspense } from "react";
import { ProductsScreen } from "@/components/catalog/desk/products-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { PRODUCT_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Sản phẩm" };

export default function DeskProductsPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={PRODUCT_SECTIONS} active="products" rows={4} />}>
      <ProductsScreen />
    </Suspense>
  );
}
