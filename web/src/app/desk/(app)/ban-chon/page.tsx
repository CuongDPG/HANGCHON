import { Suspense } from "react";
import { BoardScreen } from "@/components/selection/board-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Bàn chọn" };

/** Bàn chọn (c1–c4). Đọc ?tab= (useSearchParams) nên bọc <Suspense> (cacheComponents). */
export default function DeskSelectionPage() {
  return (
    <Suspense fallback={<DeskPageFallback title="Bàn chọn" rows={4} />}>
      <BoardScreen />
    </Suspense>
  );
}
