import { Suspense } from "react";
import { CotrialScreen } from "@/components/crm/cotrial-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Người dùng thử" };

/** «Mời thử cùng»: lời mời theo món + sổ người dùng thử. Tab đọc từ URL (?tab=) → đặt trong <Suspense>. */
export default function CotrialPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Người dùng thử" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <CotrialScreen />
    </Suspense>
  );
}
