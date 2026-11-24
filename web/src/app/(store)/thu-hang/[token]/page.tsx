import type { Metadata } from "next";
import { Suspense } from "react";
import { TesterResponse } from "@/components/crm/tester-response";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata: Metadata = { title: "Thử hàng cùng mình", robots: { index: false, follow: false } };

/** Link mời thử hàng (h8) — mỗi khách một link riêng, gửi cảm nhận một lần. Không cần tài khoản. */
export default function TesterInvitePage({ params }: PageProps<"/thu-hang/[token]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Thử hàng cùng mình" />
          <SkeletonList rows={2} />
        </div>
      }
    >
      <Invite params={params} />
    </Suspense>
  );
}

async function Invite({ params }: { params: PageProps<"/thu-hang/[token]">["params"] }) {
  const { token } = await params;
  return <TesterResponse token={token} />;
}
