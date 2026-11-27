import type { Metadata } from "next";
import { Hourglass } from "lucide-react";
import { Suspense } from "react";
import { ArrivedDropRow, OpenDropCard, UpcomingDropRow } from "@/components/catalog/drop-card";
import { StoreIntro } from "@/components/store/store-intro";
import { ButtonLink } from "@/components/ui/button";
import { SectionLabel } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { catalogApi } from "@/lib/api/catalog";
import { errorMessage } from "@/lib/api/client";

export const metadata: Metadata = {
  title: "Mua chung",
  description: "Hàng được gom đơn theo đợt: có hạn chót, số suất và ngày hàng về dự kiến nói rõ từ đầu.",
  alternates: { canonical: "/dot" },
};

/** Mua chung — đợt gom đơn (e3): đợt đang mở, sắp mở («Nhắc mình»), đã về kèm đánh giá. */
export default function DropsPage() {
  return (
    <div className="flex flex-col gap-6">
      <StoreIntro eyebrow="Mua chung" title="Mua chung để có giá tốt nhất...">
        Mình gom đơn theo đợt: hạn chót, số suất và ngày hàng về dự kiến nói rõ từ đầu.
      </StoreIntro>
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        <DropsBody />
      </Suspense>
    </div>
  );
}

async function DropsBody() {
  let data;
  try {
    data = await catalogApi.drops();
  } catch (err) {
    return <EmptyState tone="error" title="Chưa tải được các đợt" description={errorMessage(err)} />;
  }
  const empty = !data.open.length && !data.upcoming.length && !data.arrived.length;
  if (empty) {
    return (
      <EmptyState
        icon={<Hourglass />}
        title="Chưa có đợt nào đang mở"
        description="Đợt mua chung đầu tiên sẽ mở khi mình thử xong vài món. Trong lúc chờ, bạn xem kệ hàng nhé."
        action={<ButtonLink href="/">Xem kệ hàng</ButtonLink>}
      />
    );
  }
  return (
    <div className="grid gap-8 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] md:items-start">
      <div className="flex flex-col gap-4">
        {data.open.length ? (
          data.open.map((d) => <OpenDropCard key={d.id} d={d} />)
        ) : (
          <EmptyState icon={<Hourglass />} title="Chưa có đợt đang mở" description="Bấm «Nhắc mình» ở đợt sắp mở để được báo." />
        )}
      </div>
      <div className="flex flex-col gap-6">
        {data.upcoming.length ? (
          <section aria-labelledby="sap-mo">
            <SectionLabel>
              <span id="sap-mo">Sắp mở</span>
            </SectionLabel>
            <div className="divide-y divide-line">
              {data.upcoming.map((d) => (
                <UpcomingDropRow key={d.id} d={d} />
              ))}
            </div>
          </section>
        ) : null}
        {data.arrived.length ? (
          <section aria-labelledby="da-ve">
            <SectionLabel>
              <span id="da-ve">Đã về</span>
            </SectionLabel>
            <div className="divide-y divide-line">
              {data.arrived.map((d) => (
                <ArrivedDropRow key={d.id} d={d} />
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
