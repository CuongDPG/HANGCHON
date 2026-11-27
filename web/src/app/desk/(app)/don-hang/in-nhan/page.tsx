import { Suspense } from "react";
import { LabelsPrint } from "@/components/orders/labels-print";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "In nhãn" };

export default function DeskLabelsPage() {
  return (
    <Suspense fallback={<DeskPageFallback title="In nhãn" backHref="/desk/don-hang?nhom=cho_giao" rows={2} />}>
      <LabelsPrint />
    </Suspense>
  );
}
