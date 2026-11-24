import { Suspense } from "react";
import { LabelsPrint } from "@/components/orders/labels-print";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "In nhãn" };

export default function DeskLabelsPage() {
  return (
    <Suspense fallback={<SkeletonList rows={2} />}>
      <LabelsPrint />
    </Suspense>
  );
}
