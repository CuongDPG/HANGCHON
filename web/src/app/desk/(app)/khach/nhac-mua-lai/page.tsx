import { Suspense } from "react";
import { ReorderScreen } from "@/components/crm/reorder-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { KHACH_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Nhắc mua lại" };

export default function ReorderPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={KHACH_SECTIONS} active="care" />}>
      <ReorderScreen />
    </Suspense>
  );
}
