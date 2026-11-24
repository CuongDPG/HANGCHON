import { Suspense } from "react";
import { DropEditor } from "@/components/catalog/desk/drop-editor";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Sửa đợt bán" };

export default function DeskDropPage({ params }: PageProps<"/desk/san-pham/dot/[id]">) {
  return (
    <Suspense fallback={<SkeletonList rows={5} />}>
      <Editor params={params} />
    </Suspense>
  );
}

async function Editor({ params }: { params: PageProps<"/desk/san-pham/dot/[id]">["params"] }) {
  const { id } = await params;
  return <DropEditor id={id} />;
}
