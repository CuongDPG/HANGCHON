import { Suspense } from "react";
import { LivestreamDetail } from "@/components/content/livestream-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Kịch bản livestream" };

export default function Page({ params }: PageProps<"/desk/noi-dung/livestream/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/noi-dung/livestream" rows={5} />}>
      <Detail params={params} />
    </Suspense>
  );
}

async function Detail({ params }: { params: PageProps<"/desk/noi-dung/livestream/[id]">["params"] }) {
  const { id } = await params;
  return <LivestreamDetail id={id} />;
}
