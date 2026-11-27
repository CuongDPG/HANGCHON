import { Suspense } from "react";
import { CotrialOfferScreen } from "@/components/crm/cotrial-offer-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Mời thử cùng" };

/** Một lời mời «Mời thử cùng». Đọc params là dữ liệu theo request → đặt trong <Suspense>. */
export default function CotrialOfferPage({ params }: PageProps<"/desk/khach/dung-thu/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Mời thử cùng" backHref="/desk/khach/dung-thu" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Offer params={params} />
    </Suspense>
  );
}

async function Offer({ params }: { params: PageProps<"/desk/khach/dung-thu/[id]">["params"] }) {
  const { id } = await params;
  return <CotrialOfferScreen id={id} />;
}
