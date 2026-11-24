import { Suspense } from "react";
import { CustomerProfileScreen } from "@/components/crm/customer-profile";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Hồ sơ khách" };

/** Hồ sơ một khách (h4). Đọc params là dữ liệu theo request → đặt trong <Suspense>. */
export default function CustomerPage({ params }: PageProps<"/desk/khach/so-khach/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Khách" backHref="/desk/khach/so-khach" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Profile params={params} />
    </Suspense>
  );
}

async function Profile({ params }: { params: PageProps<"/desk/khach/so-khach/[id]">["params"] }) {
  const { id } = await params;
  return <CustomerProfileScreen id={id} />;
}
