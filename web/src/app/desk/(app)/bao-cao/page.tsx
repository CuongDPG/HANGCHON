import { Suspense } from "react";
import { ReportScreen } from "@/components/finance/report-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Báo cáo tuần" };

export default function DeskReportsPage() {
  return (
    <Suspense fallback={<DeskPageFallback title="Báo cáo tuần" />}>
      <ReportScreen />
    </Suspense>
  );
}
