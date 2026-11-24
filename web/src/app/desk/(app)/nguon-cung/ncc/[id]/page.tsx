import { Suspense } from "react";
import { SupplierScreen } from "@/components/supply/supplier-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Nhà cung cấp" };

export default function Page({ params }: PageProps<"/desk/nguon-cung/ncc/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Đang tải…" backHref="/desk/nguon-cung?tab=ncc" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Inner params={params} />
    </Suspense>
  );
}

async function Inner({ params }: { params: PageProps<"/desk/nguon-cung/ncc/[id]">["params"] }) {
  const { id } = await params;
  return <SupplierScreen id={id} />;
}
