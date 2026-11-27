import { Suspense } from "react";
import { CandidateScreen } from "@/components/selection/candidate-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Món trên bàn chọn" };

export default function CandidatePage({ params }: PageProps<"/desk/ban-chon/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/ban-chon" />}>
      <Candidate params={params} />
    </Suspense>
  );
}

async function Candidate({ params }: { params: PageProps<"/desk/ban-chon/[id]">["params"] }) {
  const { id } = await params;
  return <CandidateScreen id={id} />;
}
