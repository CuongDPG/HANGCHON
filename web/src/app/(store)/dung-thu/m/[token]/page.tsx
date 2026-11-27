import type { Metadata } from "next";
import { Suspense } from "react";
import { CotrialApply } from "@/components/crm/cotrial-apply";
import { PageHeader, SkeletonList } from "@/components/ui";

// link riêng chị tự gửi: không lập chỉ mục, không có trong sơ đồ trang / nguồn cấp
export const metadata: Metadata = { title: "Dùng thử cùng mình", robots: { index: false, follow: false } };

/** Lời mời «Mời thử cùng» — link riêng, không liệt kê ở đâu trên website. Không cần tài khoản. */
export default function CotrialOfferPage({ params }: PageProps<"/dung-thu/m/[token]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Dùng thử cùng mình" />
          <SkeletonList rows={2} />
        </div>
      }
    >
      <Offer params={params} />
    </Suspense>
  );
}

async function Offer({ params }: { params: PageProps<"/dung-thu/m/[token]">["params"] }) {
  const { token } = await params;
  return <CotrialApply token={token} />;
}
