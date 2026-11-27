"use client";

import { ArrowRight, PackagePlus, Sparkles } from "lucide-react";
import { useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardLink } from "@/components/ui/card";
import { DateTime } from "@/components/ui/date-time";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { Toolbar, ToolbarSearch } from "@/components/ui/toolbar";
import { notifySuccess } from "@/components/ui/toast";
import {
  PRODUCT_STATUS_LABELS,
  useDeskProducts,
  useFromCandidate,
  useProductPipeline,
  useSelectableCandidates,
  type ProductPipeline,
  type ProductStatus,
} from "@/lib/api/catalog";
import { cn } from "@/lib/cn";
import { formatVndCompact } from "@/lib/format";
import { matchesVi } from "@/lib/text";
import { PRODUCT_SECTIONS } from "@/lib/desk-sections";
import { useUrlParam } from "@/lib/use-url-param";

type Tab = "all" | ProductStatus;
export const STATUS_TONE: Record<ProductStatus, BadgeTone> = {
  draft: "outline",
  pending_review: "warning",
  published: "success",
  paused: "neutral",
  stopped: "danger",
  archived: "neutral",
};

/** Danh sách sản phẩm (e1): món AI đã dựng trang chờ chị duyệt nằm trên cùng. */
export function ProductsScreen() {
  const [tab, setTab] = useUrlParam<Tab>("tab", "all", ["all", "draft", "pending_review", "published", "paused", "stopped"]);
  const [q, setQ] = useState("");
  const { data, isPending, error } = useDeskProducts();
  const pipeline = useProductPipeline();
  const track = new Map((pipeline.data ?? []).map((x) => [x.product_id, x]));
  const selectable = useSelectableCandidates();
  const create = useFromCandidate();
  const rows = data?.items ?? [];
  const count = (s: ProductStatus) => rows.filter((r) => r.status === s).length;
  const shown = rows
    .filter((r) => tab === "all" || r.status === tab)
    .filter((r) => matchesVi(r.name, q))
    .sort((a, b) => Number(b.status === "pending_review") - Number(a.status === "pending_review"));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={PRODUCT_SECTIONS} active="products" />
      {selectable.data?.length ? (
        <Card tone="accent" className="flex flex-col gap-2">
          <p className="text-[15px] font-semibold">{selectable.data.length} món chị đã chọn chưa có trang sản phẩm</p>
          <ul className="flex flex-col gap-2">
            {selectable.data.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-[15px]">{c.title_vi}</span>
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Sparkles className="size-4" />}
                  loading={create.isPending && create.variables === c.id}
                  onClick={() => create.mutate(c.id, { onSuccess: () => notifySuccess("AI đã dựng trang, chị xem và duyệt nhé.") })}
                >
                  AI dựng trang
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      <Tabs
        aria-label="Trạng thái sản phẩm"
        value={tab}
        onChange={setTab}
        items={[
          { value: "draft", label: "Nháp", count: count("draft") },
          { value: "pending_review", label: "Chờ duyệt", count: count("pending_review") },
          { value: "published", label: "Trên kệ", count: count("published") },
          { value: "paused", label: "Tạm ẩn", count: count("paused") },
          { value: "stopped", label: "Đã ngừng bán", count: count("stopped") },
          { value: "all", label: "Tất cả", count: rows.length },
        ]}
      />
      <Toolbar
        end={<ToolbarSearch value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm sản phẩm" aria-label="Tìm sản phẩm" />}
      />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được sản phẩm" description={error.message} />
      ) : shown.length === 0 ? (
        <EmptyState
          icon={<PackagePlus />}
          title={rows.length ? "Không có sản phẩm nào ở mục này" : "Chưa có sản phẩm"}
          description="Khi chị chọn một món ở Bàn chọn, AI tự dựng trang nháp ở đây."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          <li aria-hidden className="hidden grid-cols-[3.5rem_minmax(0,1.3fr)_minmax(0,0.9fr)_minmax(0,1.5fr)_7.5rem] gap-x-3 px-3 text-[12.5px] font-semibold tracking-[0.06em] text-ink-3 uppercase md:grid">
            <span />
            <span>Món</span>
            <span>Hồ sơ chọn</span>
            <span>Hồ sơ bán: nội dung → kênh → đơn</span>
            <span className="text-right">Trang</span>
          </li>
          {shown.map((p) => (
            <li key={p.id}>
              <CardLink
                href={`/desk/san-pham/${p.id}`}
                className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 p-3 md:grid-cols-[3.5rem_minmax(0,1.3fr)_minmax(0,0.9fr)_minmax(0,1.5fr)_7.5rem]"
              >
                <div className="row-span-3 w-14 md:row-span-1">
                  <ImageBox src={p.image?.webp["400"] ?? p.image?.src_small} alt="" ratio="1/1" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-[15px] font-semibold">{p.name}</p>
                  <p className="flex flex-wrap items-center gap-x-2 text-[13px] text-ink-2">
                    {p.price_vnd ? <Money value={p.price_vnd} /> : <span className="text-seal">Chưa có giá</span>}
                    {p.review_count ? <span>{p.review_count} đánh giá</span> : null}
                  </p>
                </div>
                <div className="justify-self-end md:order-last">
                  <Badge tone={STATUS_TONE[p.status]}>{PRODUCT_STATUS_LABELS[p.status]}</Badge>
                </div>
                <SelectionCell p={p} t={track.get(p.id)} />
                <SalesCell t={track.get(p.id)} />
              </CardLink>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Chiều ngược: chọn từ bao nhiêu mẫu, ngày nào, thử bao lâu. */
function SelectionCell({ p, t }: { p: { selected_count: number; considered_count: number | null }; t?: ProductPipeline }) {
  return (
    <p className="col-span-2 col-start-2 min-w-0 text-[13px] text-ink-2 md:col-span-1 md:col-start-auto md:truncate">
      {p.considered_count ? `Chọn ${p.selected_count}/${p.considered_count} mẫu` : "Không qua Săn hàng"}
      {t?.chosen_at ? (
        <>
          {" ngày "}
          <DateTime value={t.chosen_at} format="dayMonth" />
        </>
      ) : null}
      {t?.trial_days ? ` · thử ${t.trial_days} ngày` : ""}
    </p>
  );
}

/** Chiều xuôi: nội dung x/6 → kênh đang bán → đơn. */
function SalesCell({ t }: { t?: ProductPipeline }) {
  if (!t) return <p className="col-start-2 text-[13px] text-ink-3 md:col-start-auto">…</p>;
  const full = t.content_ready === t.content_total;
  return (
    <p className="col-span-2 col-start-2 flex min-w-0 items-center gap-x-1.5 text-[13px] whitespace-nowrap md:col-span-1 md:col-start-auto" aria-label="Đường bán">
      <span className={cn("shrink-0 rounded-sm px-1.5 tabular-nums", full ? "bg-auto-wash text-auto" : "bg-soft text-ink-2")}>
        Nội dung {t.content_ready}/{t.content_total}
      </span>
      <ArrowRight aria-hidden className="size-3.5 shrink-0 text-ink-3" />
      <span className={cn("min-w-0 truncate", t.channels_live.length ? "text-ink" : "text-ink-3")} title={t.channels_live.join(", ")}>
        {t.channels_live.length ? (
          <>
            {t.channels_live.length} kênh<span className="hidden md:inline">: {t.channels_live.join(", ")}</span>
          </>
        ) : (
          "chưa lên kênh"
        )}
      </span>
      <ArrowRight aria-hidden className="size-3.5 shrink-0 text-ink-3" />
      <span className={cn("shrink-0 tabular-nums", t.orders ? "font-semibold text-ink" : "text-ink-3")}>
        {t.orders ? `${t.orders} đơn · ${formatVndCompact(t.revenue_vnd)}` : "chưa có đơn"}
      </span>
    </p>
  );
}
