import { Suspense } from "react";
import { POScreen } from "@/components/supply/po-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Đơn đặt hàng" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/don/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/nguon-cung?tab=don" />}>
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/don/[id]">["params"] }) {
  const { id } = await params;
  return <POScreen id={id} />;
}
