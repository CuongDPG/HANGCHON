import { ClipboardList } from "lucide-react";
import { Suspense } from "react";
import { PageHeader } from "@/components/ui/page-header";
import { StorePlaceholder } from "@/components/store/store-placeholder";

/** Hồ sơ chọn (e2): món được chọn đặt cạnh các món bị loại, kèm lý do. */
export default function SelectionDossierPage({ params }: PageProps<"/san-pham/[slug]/ho-so-chon">) {
  return (
    <StorePlaceholder
      title="Hồ sơ chọn"
      // Đọc params là dữ liệu theo request → đặt trong <Suspense> (cacheComponents)
      header={
        <Suspense fallback={<PageHeader title="Hồ sơ chọn" backHref="/" />}>
          <DossierHeader params={params} />
        </Suspense>
      }
      icon={<ClipboardList />}
      emptyTitle="Hồ sơ chọn đang được soạn"
      emptyDescription="Ở đây sẽ có số món đã xem, đã mua thử, lý do loại từng món, và phần nào AI làm, phần nào chị làm."
    />
  );
}

async function DossierHeader({ params }: { params: PageProps<"/san-pham/[slug]/ho-so-chon">["params"] }) {
  const { slug } = await params;
  return <PageHeader title="Hồ sơ chọn" backHref={`/san-pham/${encodeURIComponent(slug)}`} />;
}
