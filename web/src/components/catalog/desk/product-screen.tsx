"use client";

import { DeskMoreMenu } from "@/components/desk/desk-more-menu";
import { relatedItems } from "@/components/desk/related-links";
import { Badge } from "@/components/ui/badge";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { useSession } from "@/lib/api/auth";
import { PRODUCT_STATUS_LABELS, useDeskProduct } from "@/lib/api/catalog";
import { useUrlParam } from "@/lib/use-url-param";
import { CommerceForm } from "./product-editor";
import { STATUS_TONE } from "./products-screen";
import { SalesDossierView } from "./sales-dossier";
import { SelectionTrailView } from "./selection-trail";
import { StopFollowUp, StopSellingButton } from "./stop-selling";

type Tab = "chon" | "ban" | "gia";
const TABS: { value: Tab; label: string }[] = [
  { value: "chon", label: "Hồ sơ chọn" },
  { value: "ban", label: "Hồ sơ bán" },
  { value: "gia", label: "Giá và cách bán" },
];

/**
 * Một sản phẩm, theo dõi hai chiều. «Hồ sơ chọn» lần ngược quá trình chọn (chỉ đọc, sửa ở trang của từng bước);
 * «Hồ sơ bán» đi xuôi đường bán: nội dung → lên kênh → khách hàng; «Giá và cách bán» là phần sửa của trang này.
 */
export function ProductScreen({ id }: { id: string }) {
  const [tab, setTab] = useUrlParam<Tab>("tab", "chon", ["chon", "ban", "gia"]);
  const { data: p, isPending, error } = useDeskProduct(id);
  const isOwner = useSession().user?.role === "owner";

  if (isPending)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader loading backHref="/desk/san-pham" />
        <SkeletonList rows={6} />
      </div>
    );
  if (error || !p)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được sản phẩm" backHref="/desk/san-pham" />
        <EmptyState tone="error" title="Chưa tải được sản phẩm" description={error?.message} />
      </div>
    );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={p.name}
        eyebrow={p.candidate_title && p.candidate_title !== p.name ? `Từ ứng viên: ${p.candidate_title}` : undefined}
        badge={<Badge tone={STATUS_TONE[p.status]}>{PRODUCT_STATUS_LABELS[p.status]}</Badge>}
        backHref="/desk/san-pham"
        actions={
          <>
            {isOwner ? <StopSellingButton product={p} size="sm" /> : null}
            <DeskMoreMenu
              items={relatedItems([
                p.candidate_id && { href: `/desk/ban-chon/${p.candidate_id}`, label: "Bàn chọn" },
                { href: `/desk/noi-dung/san-pham/${p.id}`, label: "Nội dung các kênh" },
                p.status === "published" && { href: `/san-pham/${p.slug}`, label: "Xem trên web" },
              ])}
            />
          </>
        }
      />
      {p.status === "stopped" ? <StopFollowUp productId={p.id} /> : null}
      <Tabs aria-label="Hồ sơ sản phẩm" value={tab} onChange={setTab} items={TABS} />
      {tab === "chon" ? <SelectionTrailView productId={p.id} /> : null}
      {tab === "ban" ? <SalesDossierView productId={p.id} slug={p.slug} /> : null}
      {tab === "gia" ? <CommerceForm p={p} /> : null}
    </div>
  );
}
