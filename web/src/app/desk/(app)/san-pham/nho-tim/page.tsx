import { Suspense } from "react";
import { FindsScreen } from "@/components/catalog/desk/finds-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { PRODUCT_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Nhờ tìm" };

export default function DeskFindsPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={PRODUCT_SECTIONS} active="finds" />}>
      <FindsScreen />
    </Suspense>
  );
}
