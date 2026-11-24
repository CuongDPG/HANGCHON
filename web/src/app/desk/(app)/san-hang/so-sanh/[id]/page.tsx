import { Suspense } from "react";
import { SkeletonList } from "@/components/ui";
import { ComparisonScreen } from "@/components/assessment/comparison-screen";

export const metadata = { title: "So sánh cạnh nhau" };

/** Bảng so sánh 2–5 ứng viên cùng đề (b3). */
export default function ComparisonPage({ params }: PageProps<"/desk/san-hang/so-sanh/[id]">) {
  return (
    <Suspense fallback={<SkeletonList rows={5} />}>
      <Comparison params={params} />
    </Suspense>
  );
}

async function Comparison({ params }: { params: PageProps<"/desk/san-hang/so-sanh/[id]">["params"] }) {
  const { id } = await params;
  return <ComparisonScreen id={id} />;
}
