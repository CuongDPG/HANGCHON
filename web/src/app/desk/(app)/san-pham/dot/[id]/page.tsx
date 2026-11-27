import { Suspense } from "react";
import { DropEditor } from "@/components/catalog/desk/drop-editor";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Sửa đợt bán" };

export default function DeskDropPage({ params }: PageProps<"/desk/san-pham/dot/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/san-pham/dot" rows={5} />}>
      <Editor params={params} />
    </Suspense>
  );
}

async function Editor({ params }: { params: PageProps<"/desk/san-pham/dot/[id]">["params"] }) {
  const { id } = await params;
  return <DropEditor id={id} />;
}
