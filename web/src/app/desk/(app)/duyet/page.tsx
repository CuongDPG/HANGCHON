import { Suspense } from "react";
import { ApprovalsScreen } from "@/components/control/approvals-screen";
import { SkeletonList } from "@/components/ui";

export const metadata = { title: "Chờ duyệt" };

export default function DeskApprovalsPage() {
  return (
    <Suspense fallback={<SkeletonList rows={4} />}>
      <ApprovalsScreen />
    </Suspense>
  );
}
