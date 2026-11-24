import { Suspense } from "react";
import { LivestreamDetail } from "@/components/content/livestream-screen";
import { SkeletonList } from "@/components/ui";

export const metadata = { title: "Kịch bản livestream" };

export default function Page({ params }: PageProps<"/desk/noi-dung/livestream/[id]">) {
  return (
    <Suspense fallback={<SkeletonList rows={5} />}>
      <Detail params={params} />
    </Suspense>
  );
}

async function Detail({ params }: { params: PageProps<"/desk/noi-dung/livestream/[id]">["params"] }) {
  const { id } = await params;
  return <LivestreamDetail id={id} />;
}
