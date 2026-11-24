import { Suspense } from "react";
import { InboundScreen } from "@/components/supply/inbound-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Lô hàng về" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/lo/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Đang tải…" backHref="/desk/nguon-cung?tab=lo-hang" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/lo/[id]">["params"] }) {
  const { id } = await params;
  return <InboundScreen id={id} />;
}
