import { Suspense } from "react";
import { SupplyScreen } from "@/components/supply/supply-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { SUPPLY_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Nguồn cung" };

/** Nguồn cung (d1–d7). Đọc ?tab= (useSearchParams) nên bọc <Suspense> (cacheComponents). */
export default function DeskSupplyPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={SUPPLY_SECTIONS} active="don" rows={4} />}>
      <SupplyScreen />
    </Suspense>
  );
}
