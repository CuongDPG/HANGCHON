import { Suspense } from "react";
import { ActivityScreen } from "@/components/control/activity-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { AI_LOG_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Nhật ký AI" };

export default function DeskAILogPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={AI_LOG_SECTIONS} active="ai" rows={4} />}>
      <ActivityScreen />
    </Suspense>
  );
}
