"use client";

import { DeskMoreMenu } from "@/components/desk/desk-more-menu";
import { PageHeader, Tabs } from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useBriefs, useDemand, useTrends } from "@/lib/api/sourcing";
import { useUrlParam } from "@/lib/use-url-param";
import { BriefComposer } from "./brief-composer";
import { BriefList } from "./brief-list";
import { CLIPPER_CARD_ID } from "./clipper-card";
import { DemandPanel } from "./demand-panel";
import { TrendsPanel } from "./trends-panel";

type Tab = "de-tim" | "xu-huong" | "khach-hoi";

export function SourcingScreen() {
  const [tab, setTab] = useUrlParam<Tab>("tab", "de-tim", ["de-tim", "xu-huong", "khach-hoi"]);
  const briefs = useBriefs("active");
  const trends = useTrends();
  const demand = useDemand();
  const running = briefs.data?.total ?? 0;
  const owner = isOwner(useSession().user);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Săn hàng"
        actions={<DeskMoreMenu items={[owner && { label: "Nút Gửi sang Hàng Chọn", href: `/desk/cai-dat/nguon-hang#${CLIPPER_CARD_ID}` }]} />}
        settings={{ href: "/desk/san-hang/khung-cham", label: "Khung chấm điểm" }}
      />
      <Tabs
        aria-label="Khu săn hàng"
        value={tab}
        onChange={setTab}
        items={[
          { value: "de-tim", label: "Đề tìm", count: running || undefined },
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
