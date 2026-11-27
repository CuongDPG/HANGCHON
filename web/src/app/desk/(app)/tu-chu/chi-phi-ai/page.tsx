import { Suspense } from "react";
import { AICostsScreen } from "@/components/control/ai-costs-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { AUTONOMY_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Chi phí AI" };

export default function DeskAICostsPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={AUTONOMY_SECTIONS} active="costs" />}>
      <AICostsScreen />
    </Suspense>
  );
}
