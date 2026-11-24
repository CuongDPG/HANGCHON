import { Suspense } from "react";
import { SupplyScreen } from "@/components/supply/supply-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Nguồn cung" };

/** Nguồn cung (d1–d7). Đọc ?tab= (useSearchParams) nên bọc <Suspense> (cacheComponents). */
export default function DeskSupplyPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Nguồn cung" />
          <SkeletonList rows={4} />
        </div>
      }
    >
      <SupplyScreen />
    </Suspense>
  );
}
