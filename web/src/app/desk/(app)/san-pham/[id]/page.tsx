import { Suspense } from "react";
import { ProductEditor } from "@/components/catalog/desk/product-editor";
import { SkeletonList } from "@/components/ui/feedback";

export const metadata = { title: "Sửa sản phẩm" };

export default function DeskProductPage({ params }: PageProps<"/desk/san-pham/[id]">) {
  return (
    <Suspense fallback={<SkeletonList rows={6} />}>
      <Editor params={params} />
    </Suspense>
  );
}

async function Editor({ params }: { params: PageProps<"/desk/san-pham/[id]">["params"] }) {
  const { id } = await params;
  return <ProductEditor id={id} />;
}
