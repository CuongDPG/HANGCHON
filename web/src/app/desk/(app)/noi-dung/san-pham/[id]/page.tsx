import { Suspense } from "react";
import { StudioScreen } from "@/components/content/studio-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Xưởng nội dung" };

/** Xưởng nội dung của một sản phẩm (f1, f5): tab theo kênh, xem trước, viết lại nhanh, duyệt và xếp lịch. */
export default function Page({ params }: PageProps<"/desk/noi-dung/san-pham/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/noi-dung" rows={4} />}>
      <Studio params={params} />
    </Suspense>
  );
}

async function Studio({ params }: { params: PageProps<"/desk/noi-dung/san-pham/[id]">["params"] }) {
  const { id } = await params;
  return <StudioScreen kind="product" id={id} />;
}
