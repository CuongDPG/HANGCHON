import { Suspense } from "react";
import { CotrialScreen } from "@/components/crm/cotrial-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { KHACH_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Người dùng thử" };

/** «Mời thử cùng»: lời mời theo món + sổ người dùng thử. Tab đọc từ URL (?tab=) → đặt trong <Suspense>. */
export default function CotrialPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={KHACH_SECTIONS} active="trial" />}>
      <CotrialScreen />
    </Suspense>
  );
}
