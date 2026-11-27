import { Suspense } from "react";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { SourcingScreen } from "@/components/sourcing/sourcing-screen";

export const metadata = { title: "Săn hàng" };

/** Săn hàng (a1–a7): ra đề, dán link, tìm bằng ảnh, đề đang chạy, radar xu hướng, khách hỏi. */
export default function DeskSourcingPage() {
  // SourcingScreen đọc ?tab= (useSearchParams) → nằm trong <Suspense> (cacheComponents)
  return (
    <Suspense fallback={<DeskPageFallback title="Săn hàng" rows={4} />}>
      <SourcingScreen />
    </Suspense>
  );
}
