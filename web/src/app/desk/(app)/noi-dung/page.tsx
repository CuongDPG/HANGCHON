import { Suspense } from "react";
import { ContentHome } from "@/components/content/content-home";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { CONTENT_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Nội dung" };

export default function DeskContentPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={CONTENT_SECTIONS} active="studio" rows={4} />}>
      <ContentHome />
    </Suspense>
  );
}
