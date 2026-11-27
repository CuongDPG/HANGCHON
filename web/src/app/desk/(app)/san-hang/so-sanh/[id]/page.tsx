import { Suspense } from "react";
import { ComparisonScreen } from "@/components/assessment/comparison-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "So sánh cạnh nhau" };

/** Bảng so sánh 2–5 ứng viên cùng đề (b3). */
export default function ComparisonPage({ params }: PageProps<"/desk/san-hang/so-sanh/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/san-hang" rows={5} />}>
      <Comparison params={params} />
    </Suspense>
  );
}

async function Comparison({ params }: { params: PageProps<"/desk/san-hang/so-sanh/[id]">["params"] }) {
  const { id } = await params;
  return <ComparisonScreen id={id} />;
}
