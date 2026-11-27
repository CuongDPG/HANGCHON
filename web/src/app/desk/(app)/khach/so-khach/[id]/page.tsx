import { Suspense } from "react";
import { CustomerProfileScreen } from "@/components/crm/customer-profile";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Hồ sơ khách" };

/** Hồ sơ một khách (h4). Đọc params là dữ liệu theo request → đặt trong <Suspense>. */
export default function CustomerPage({ params }: PageProps<"/desk/khach/so-khach/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/khach/so-khach" />}>
      <Profile params={params} />
    </Suspense>
  );
}

async function Profile({ params }: { params: PageProps<"/desk/khach/so-khach/[id]">["params"] }) {
  const { id } = await params;
  return <CustomerProfileScreen id={id} />;
}
