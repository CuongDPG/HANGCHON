import { Suspense } from "react";
import { StudioScreen } from "@/components/content/studio-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Bài mở đợt" };

/** Bài báo mở đợt (Facebook, Instagram, Zalo) cho một đợt bán. */
export default function Page({ params }: PageProps<"/desk/noi-dung/dot/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/noi-dung" rows={4} />}>
      <Studio params={params} />
    </Suspense>
  );
}

async function Studio({ params }: { params: PageProps<"/desk/noi-dung/dot/[id]">["params"] }) {
  const { id } = await params;
  return <StudioScreen kind="drop" id={id} />;
}
