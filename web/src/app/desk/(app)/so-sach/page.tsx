import { Suspense } from "react";
import { BooksScreen } from "@/components/finance/books-screen";
import { SkeletonList } from "@/components/ui";

export const metadata = { title: "Sổ sách" };

export default function DeskBooksPage() {
  return (
    <Suspense fallback={<SkeletonList rows={4} />}>
      <BooksScreen />
    </Suspense>
  );
}
