import { Suspense } from "react";
import { SupplierScreen } from "@/components/supply/supplier-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Nhà cung cấp" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/ncc/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/nguon-cung?tab=ncc" />}>
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/ncc/[id]">["params"] }) {
  const { id } = await params;
  return <SupplierScreen id={id} />;
}
