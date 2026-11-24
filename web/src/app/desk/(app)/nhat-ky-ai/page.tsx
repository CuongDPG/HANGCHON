import { Suspense } from "react";
import { ActivityScreen } from "@/components/control/activity-screen";
import { SkeletonList } from "@/components/ui";

export const metadata = { title: "Nhật ký AI" };

export default function DeskAILogPage() {
  return (
    <Suspense fallback={<SkeletonList rows={4} />}>
      <ActivityScreen />
    </Suspense>
  );
}
