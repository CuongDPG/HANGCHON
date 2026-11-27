import { Suspense } from "react";
import { BooksScreen } from "@/components/finance/books-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { BOOKS_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Sổ sách" };

export default function DeskBooksPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={BOOKS_SECTIONS} active="so" rows={4} />}>
      <BooksScreen />
    </Suspense>
  );
}
