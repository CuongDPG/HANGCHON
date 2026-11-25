import type { Metadata } from "next";
import { Suspense } from "react";
import { FunnelStrip } from "@/components/catalog/funnel-strip";
import { getDossier } from "@/components/catalog/product-data";
import { Badge } from "@/components/ui/badge";
import { Card, SectionLabel } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { Seal } from "@/components/ui/seal";
import type { Alternative } from "@/lib/api/catalog";

export async function generateMetadata({ params }: PageProps<"/san-pham/[slug]/ho-so-chon">): Promise<Metadata> {
  const { slug } = await params;
  const d = await getDossier(slug);
  const f = d.funnel;
  return {
    title: `Hồ sơ chọn: ${d.product.name}`,
    description: `Xem ${f.viewed ?? "nhiều"} mẫu, mua thử ${f.tried ?? 0}, chọn ${f.selected ?? 1}. Lý do loại từng mẫu, không nêu tên thương hiệu.`,
    alternates: { canonical: `/san-pham/${slug}/ho-so-chon` },
  };
}

/** Hồ sơ chọn (e2): món được chọn đặt cạnh các món bị loại, kèm lý do. Món bị loại không nêu tên thương hiệu. */
export default function SelectionDossierPage({ params }: PageProps<"/san-pham/[slug]/ho-so-chon">) {
  return (
    <Suspense fallback={<DossierSkeleton />}>
      <DossierBody params={params} />
    </Suspense>
  );
}

function DossierSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Đang tải hồ sơ chọn">
      <PageHeader title="Hồ sơ chọn" backHref="/" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-28 w-full" />
    </div>
  );
}

function shortName(name: string) {
  return name.replace(/\s+\d+([.,]\d+)?\s*(ml|l|cm|g|kg)\b.*$/i, "").trim() || name;
}

async function DossierBody({ params }: { params: PageProps<"/san-pham/[slug]/ho-so-chon">["params"] }) {
  const { slug } = await params;
  const d = await getDossier(slug);
  const p = d.product;
  const f = d.funnel;
  const title = `${shortName(p.name)}: xem ${f.viewed ?? "?"}, mua thử ${f.tried ?? 0}, chọn ${f.selected ?? 1}`;
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} eyebrow="Hồ sơ chọn" backHref={`/san-pham/${p.slug}`} />
      <FunnelStrip funnel={f} />

      <section className="flex flex-col gap-3" aria-label="Món được chọn và các món bị loại">
        <Card tone="accent" className="flex items-center gap-3">
          <div className="w-16 shrink-0">
            <ImageBox src={p.image?.webp["400"] ?? p.image?.src_small} alt={p.name} ratio="1/1" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold">
              Mẫu A{p.origin ? ` · ${p.origin}` : ""} · <Money value={p.price_vnd} />
            </p>
            {p.summary ? <p className="mt-0.5 text-[13px] text-ink-2">{p.summary}</p> : null}
            {p.trial_days ? <p className="mt-0.5 text-[13px] text-ink-2">Dùng thử {p.trial_days} ngày</p> : null}
          </div>
          <Seal size={44} />
        </Card>
        {d.alternatives.map((a) => (
          <AlternativeCard key={a.label} a={a} />
        ))}
        {d.alternatives.length === 0 ? (
          <p className="text-[14px] text-ink-2">Các mẫu còn lại bị loại ngay từ vòng đọc đánh giá.</p>
        ) : null}
      </section>

      {d.reject_groups.length ? (
        <section className="flex flex-col gap-2" aria-labelledby="nhom-ly-do">
          <SectionLabel>
            <span id="nhom-ly-do">
              {d.screened_out ? `${d.screened_out} mẫu loại từ vòng đọc đánh giá` : "Lý do loại"}
            </span>
          </SectionLabel>
          <ul className="flex flex-wrap gap-2">
            {d.reject_groups.map((g) => (
              <li key={g.key} className="rounded-md border border-line-strong bg-surface px-3 py-1.5 text-[14px]">
                {g.label} <span className="tabular-nums text-ink-3">· {g.count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {p.reason_selected.length || p.not_satisfied ? (
        <Card tone="soft">
          {p.reason_selected.length ? (
            <>
              <h2 className="text-[17px] font-bold">Vì sao mẫu A được chọn</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[15px]">
                {p.reason_selected.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </>
          ) : null}
          {p.not_satisfied ? (
            <p className="mt-3 text-[15px]">
              <span className="font-semibold">Điều mình chưa ưng:</span> {p.not_satisfied}
            </p>
          ) : null}
        </Card>
      ) : null}

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
    </Card>
  );
}

