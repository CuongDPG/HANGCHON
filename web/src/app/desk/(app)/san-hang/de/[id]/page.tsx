import { Suspense } from "react";
import { SkeletonList } from "@/components/ui";
import { BriefScreen } from "@/components/sourcing/brief-screen";

export const metadata = { title: "Đề tìm" };

/** Một đề tìm: AI hiểu là (chip sửa được), tiến độ quét, ứng viên xếp hạng, so sánh, săn theo lịch. */
export default function BriefPage({ params }: PageProps<"/desk/san-hang/de/[id]">) {
  return (
    <Suspense fallback={<SkeletonList rows={4} />}>
      <Brief params={params} />
    </Suspense>
  );
}

async function Brief({ params }: { params: PageProps<"/desk/san-hang/de/[id]">["params"] }) {
  const { id } = await params;
  return <BriefScreen id={id} />;
}
