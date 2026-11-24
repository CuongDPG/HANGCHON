"use client";

import { PackagePlus, Search, Sparkles } from "lucide-react";
import { useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardLink } from "@/components/ui/card";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { notifySuccess } from "@/components/ui/toast";
import {
  PRODUCT_STATUS_LABELS,
  useDeskProducts,
  useFromCandidate,
  useSelectableCandidates,
  type ProductStatus,
} from "@/lib/api/catalog";
import { matchesVi } from "@/lib/text";
import { DeskSubnav } from "./desk-subnav";

type Tab = "all" | ProductStatus;
export const STATUS_TONE: Record<ProductStatus, BadgeTone> = {
  draft: "outline",
  pending_review: "warning",
  published: "success",
  paused: "neutral",
  archived: "neutral",
};

/** Danh sách sản phẩm (e1): món AI đã dựng trang chờ chị duyệt nằm trên cùng. */
export function ProductsScreen() {
  const [tab, setTab] = useState<Tab>("all");
  const [q, setQ] = useState("");
  const { data, isPending, error } = useDeskProducts();
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
      <PageHeader title="Sản phẩm" description="Trang sản phẩm do AI dựng từ hồ sơ chọn. Chị sửa lời, đặt giá, duyệt thì món lên kệ." />
      <DeskSubnav active="products" />
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
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm sản phẩm" aria-label="Tìm sản phẩm" leading={<Search />} />
      <Tabs
        aria-label="Trạng thái sản phẩm"
        value={tab}
        onChange={setTab}
        items={[
          { value: "all", label: "Tất cả", count: rows.length },
          { value: "pending_review", label: "Chờ duyệt", count: count("pending_review") },
          { value: "published", label: "Trên kệ", count: count("published") },
          { value: "draft", label: "Nháp", count: count("draft") },
          { value: "paused", label: "Tạm ẩn", count: count("paused") },
        ]}
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
          {shown.map((p) => (
            <li key={p.id}>
              <CardLink href={`/desk/san-pham/${p.id}`} className="flex items-center gap-3 p-3">
                <div className="w-14 shrink-0">
                  <ImageBox src={p.image?.webp["400"] ?? p.image?.src_small} alt="" ratio="1/1" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-semibold">{p.name}</p>
                  <p className="flex flex-wrap items-center gap-x-2 text-[13px] text-ink-2">
                    {p.price_vnd ? <Money value={p.price_vnd} /> : <span className="text-seal">Chưa có giá</span>}
                    {p.considered_count ? <span>Chọn {p.selected_count}/{p.considered_count}</span> : null}
                    {p.review_count ? <span>{p.review_count} đánh giá</span> : null}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[p.status]}>{PRODUCT_STATUS_LABELS[p.status]}</Badge>
              </CardLink>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
