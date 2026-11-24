import { Suspense } from "react";
import { CostScreen } from "@/components/supply/cost-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Giá vốn về tay" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/gia-von/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Đang tải…" backHref="/desk/nguon-cung?tab=gia-von" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/gia-von/[id]">["params"] }) {
  const { id } = await params;
  return <CostScreen candidateId={id} />;
}
