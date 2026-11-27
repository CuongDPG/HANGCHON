import { Suspense } from "react";
import { ApprovalsScreen } from "@/components/control/approvals-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Chờ duyệt" };

export default function DeskApprovalsPage() {
  return (
    <Suspense fallback={<DeskPageFallback title="Chờ duyệt" rows={4} />}>
      <ApprovalsScreen />
    </Suspense>
  );
}
