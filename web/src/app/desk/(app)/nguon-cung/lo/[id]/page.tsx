import { Suspense } from "react";
import { InboundScreen } from "@/components/supply/inbound-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Lô hàng về" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/lo/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/nguon-cung?tab=lo-hang" />}>
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/lo/[id]">["params"] }) {
  const { id } = await params;
  return <InboundScreen id={id} />;
}
