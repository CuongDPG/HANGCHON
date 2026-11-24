import { Suspense } from "react";
import { SkeletonList } from "@/components/ui";
import { SourcingScreen } from "@/components/sourcing/sourcing-screen";

export const metadata = { title: "Săn hàng" };

/** Săn hàng (a1–a7): ra đề, dán link, tìm bằng ảnh, đề đang chạy, radar xu hướng, khách hỏi. */
export default function DeskSourcingPage() {
  // SourcingScreen đọc ?tab= (useSearchParams) → nằm trong <Suspense> (cacheComponents)
  return (
    <Suspense fallback={<SkeletonList rows={4} />}>
      <SourcingScreen />
    </Suspense>
  );
}
