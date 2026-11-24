import { Suspense } from "react";
import { POScreen } from "@/components/supply/po-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Đơn đặt hàng" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/don/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Đang tải…" backHref="/desk/nguon-cung?tab=don" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/don/[id]">["params"] }) {
  const { id } = await params;
  return <POScreen id={id} />;
}
