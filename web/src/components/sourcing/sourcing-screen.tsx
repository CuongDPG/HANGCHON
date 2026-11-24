"use client";

import { SlidersHorizontal } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { IconLink, PageHeader, Tabs } from "@/components/ui";
import { useBriefs, useDemand, useTrends } from "@/lib/api/sourcing";
import { BriefComposer } from "./brief-composer";
import { BriefList } from "./brief-list";
import { DemandPanel } from "./demand-panel";
import { TrendsPanel } from "./trends-panel";

type Tab = "de-tim" | "xu-huong" | "khach-hoi";

export function SourcingScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = raw === "xu-huong" || raw === "khach-hoi" ? raw : "de-tim";
  const briefs = useBriefs("active");
  const trends = useTrends();
  const demand = useDemand();
  const running = briefs.data?.total ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Săn hàng"
        description={running ? `${running} đề đang chạy` : "Chị ra đề bằng lời, AI cho biết nó hiểu thế nào rồi mới tìm."}
        actions={<IconLink href="/desk/san-hang/khung-cham" label="Khung chấm điểm" icon={<SlidersHorizontal />} />}
      />
      <Tabs
        aria-label="Khu săn hàng"
        value={tab}
        onChange={(v) => router.replace(v === "de-tim" ? pathname : `${pathname}?tab=${v}`, { scroll: false })}
        items={[
          { value: "de-tim", label: "Đề tìm" },
          { value: "xu-huong", label: "Xu hướng", count: trends.data?.items.filter((t) => t.status === "new").length || undefined },
          { value: "khach-hoi", label: "Khách hỏi", count: demand.data?.items.filter((d) => d.status === "open").length || undefined },
        ]}
      />
      {tab === "de-tim" ? (
        <>
          <BriefComposer />
          <BriefList />
        </>
      ) : tab === "xu-huong" ? (
        <TrendsPanel />
      ) : (
        <DemandPanel />
      )}
    </div>
  );
}
