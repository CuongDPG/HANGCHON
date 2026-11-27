import { Suspense } from "react";
import { CostScreen } from "@/components/supply/cost-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Giá vốn về tay" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/gia-von/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/nguon-cung?tab=gia-von" />}>
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/gia-von/[id]">["params"] }) {
  const { id } = await params;
  return <CostScreen candidateId={id} />;
}
