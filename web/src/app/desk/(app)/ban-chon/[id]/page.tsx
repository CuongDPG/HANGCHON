import { Suspense } from "react";
import { CandidateScreen } from "@/components/selection/candidate-screen";
import { PageHeader, SkeletonList } from "@/components/ui";

export const metadata = { title: "Món trên bàn chọn" };

export default function CandidatePage({ params }: PageProps<"/desk/ban-chon/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4">
          <PageHeader title="Đang tải…" backHref="/desk/ban-chon" />
          <SkeletonList rows={3} />
        </div>
      }
    >
      <Candidate params={params} />
    </Suspense>
  );
}

async function Candidate({ params }: { params: PageProps<"/desk/ban-chon/[id]">["params"] }) {
  const { id } = await params;
  return <CandidateScreen id={id} />;
}
