import { Suspense } from "react";
import { BoardScreen } from "@/components/selection/board-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Bàn chọn" };

/** Bàn chọn (c1–c4). Đọc ?tab= (useSearchParams) nên bọc <Suspense> (cacheComponents). */
export default function DeskSelectionPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Bàn chọn" />
          <SkeletonList rows={4} />
        </div>
      }
    >
      <BoardScreen />
    </Suspense>
  );
}
