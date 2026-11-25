"use client";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { Seal } from "@/components/ui/seal";
import { useDeskDossier, type Alternative } from "@/lib/api/catalog";
import { formatNumber } from "@/lib/format";
import { FunnelStrip } from "./funnel-strip";

/**
 * Hồ sơ chọn (e2) ở desk: dải số sàng lọc, món được chọn đặt cạnh từng món đã loại kèm lý do, nhóm lý do loại.
 * Đây là dữ liệu theo dõi nội bộ — website chỉ hiện mô tả và «Vì sao mình chọn», không hiện quá trình chọn.
 */
export function SelectionDossier({ productId }: { productId: string }) {
  const { data: d, isPending, error } = useDeskDossier(productId);
  if (isPending) return <SkeletonList rows={3} />;
  if (error || !d) return <EmptyState tone="error" title="Chưa tải được hồ sơ chọn" description={error?.message} />;
  const p = d.product;
  const hasFunnel = Object.values(d.funnel).some((v) => v !== null && v !== undefined);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        {p.seal.total ? <Seal chosen={p.seal.chosen} total={p.seal.total} size={52} /> : null}
        {hasFunnel ? <FunnelStrip funnel={d.funnel} className="flex-1" /> : <p className="text-[14px] text-ink-2">Chưa có số liệu sàng lọc.</p>}
      </div>

      <div className="grid gap-3 lg:grid-cols-2" aria-label="Món được chọn và các món đã loại">
        <Card tone="accent" className="flex items-center gap-3">
          <div className="w-16 shrink-0">
            <ImageBox src={p.image?.webp["400"] ?? p.image?.src_small} alt={p.name} ratio="1/1" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold">
              Mẫu A (đã chọn){p.origin ? ` · ${p.origin}` : ""} · <Money value={p.price_vnd} />
            </p>
            {p.summary ? <p className="mt-0.5 text-[13px] text-ink-2">{p.summary}</p> : null}
            {p.trial_days ? <p className="mt-0.5 text-[13px] text-ink-2">Chị dùng thử {p.trial_days} ngày</p> : null}
          </div>
          <Seal size={44} />
        </Card>
        {d.alternatives.map((a) => (
          <AlternativeCard key={a.label} a={a} />
        ))}
      </div>
      {d.alternatives.length === 0 ? (
        <p className="text-[14px] text-ink-2">Không có món nào được so kỹ hay mua thử: các mẫu còn lại bị loại từ vòng đọc đánh giá.</p>
      ) : null}

      {d.reject_groups.length ? (
        <div className="flex flex-col gap-2">
          <p className="text-[14px] font-semibold">Nhóm lý do loại</p>
          <ul className="flex flex-wrap gap-2">
            {d.reject_groups.map((g) => (
              <li key={g.key} className="rounded-md border border-line-strong bg-surface px-3 py-1.5 text-[14px]">
                {g.label} <span className="tabular-nums text-ink-3">· {g.count}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-[14px] text-ink-2">
        {d.screened_out ? `${formatNumber(d.screened_out)} mẫu loại từ vòng đọc đánh giá` : "Không mẫu nào bị loại từ vòng đọc đánh giá"}
        {d.reviews_read
          ? ` · đã đọc ${formatNumber(d.reviews_read)} đánh giá${d.review_languages.length ? ` (${d.review_languages.join(", ")})` : ""}`
          : ""}
        .
      </p>
      <p className="text-[12.5px] text-ink-3">
        Món bị loại hiện không kèm tên thương hiệu hay tên shop. Hồ sơ này chỉ để chị theo dõi, không hiện trên website.
      </p>
    </div>
  );
}

function AlternativeCard({ a }: { a: Alternative }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[15px] font-semibold">
          {a.label}
          {a.origin ? ` · ${a.origin}` : ""}
          {a.price_vnd ? (
            <>
              {" · "}
              <span className="font-normal text-ink-2">
                giá nguồn ~<Money value={a.price_vnd} />
              </span>
            </>
          ) : null}
        </p>
        <Badge tone={a.stage === "tried" ? "warning" : "outline"}>{a.stage === "tried" ? "Đã mua thử" : "So kỹ"}</Badge>
      </div>
      {a.summary ? <p className="mt-0.5 text-[13px] text-ink-2">{a.summary}</p> : null}
      {a.reason ? (
        <p className="mt-2 text-[15px]">
          <span className="font-semibold text-seal">Loại:</span> {a.reason}
        </p>
      ) : null}
      {a.tags.length ? <p className="mt-1 text-[13px] text-ink-3">{a.tags.join(" · ")}</p> : null}
    </Card>
  );
}
