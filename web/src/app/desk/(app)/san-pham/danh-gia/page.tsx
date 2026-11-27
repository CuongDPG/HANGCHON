import { Suspense } from "react";
import { ReviewsScreen } from "@/components/catalog/desk/reviews-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { PRODUCT_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Đánh giá chờ duyệt" };

export default function DeskReviewsPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={PRODUCT_SECTIONS} active="reviews" />}>
      <ReviewsScreen />
    </Suspense>
  );
}
