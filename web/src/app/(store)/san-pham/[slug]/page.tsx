import type { Metadata } from "next";
import { CircleAlert, Hourglass, MessageCircleQuestion } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import { AskBox } from "@/components/assistant/ask-box";
import { Countdown } from "@/components/catalog/countdown";
import { PlainText } from "@/components/catalog/plain-text";
import { getProduct, productJsonLd } from "@/components/catalog/product-data";
import { Stars } from "@/components/catalog/stars";
import { BuyBox } from "@/components/orders/buy-box";
import { JsonLd } from "@/components/store/json-ld";
import { Badge } from "@/components/ui/badge";
import { Card, SectionLabel } from "@/components/ui/card";
import { DataList } from "@/components/ui/data-display";
import { Skeleton } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { Seal } from "@/components/ui/seal";
import type { ProductDetail } from "@/lib/api/catalog";
import { siteUrl } from "@/lib/api/catalog";
import { formatDate, formatDayMonth } from "@/lib/format";
import { ownerReplyLabel } from "@/lib/picker";

export async function generateMetadata({ params }: PageProps<"/san-pham/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const p = await getProduct(slug);
  const title = p.seo_title || p.name;
  const description =
    p.seo_description ||
    p.short_description ||
    `${p.name}${p.seal.total ? ` — chọn ${p.seal.chosen} trong ${p.seal.total} mẫu` : ""}${p.proof ? `, ${p.proof.toLowerCase()}` : ""}.`;
  const image = p.images[0]?.src_large ?? p.images[0]?.src ?? undefined;
  return {
    title,
    description,
    alternates: { canonical: `/san-pham/${p.slug}` },
    metadataBase: new URL(siteUrl()),
    openGraph: {
      type: "website",
      locale: "vi_VN",
      siteName: "Hàng Chọn",
      title: p.name,
      description,
      url: `/san-pham/${p.slug}`,
      images: image ? [{ url: image, width: 1600, height: 1600, alt: p.name }] : undefined,
    },
    other: { "product:price:amount": String(p.price_vnd), "product:price:currency": "VND" },
  };
}

/** Trang sản phẩm (e1, e2, e7, e8): lý do chọn đứng trước thông số, có cả điều chưa ưng. */
export default function ProductPage({ params }: PageProps<"/san-pham/[slug]">) {
  return (
    <Suspense fallback={<ProductSkeleton />}>
      <ProductBody params={params} />
    </Suspense>
  );
}

function ProductSkeleton() {
  return (
    <div className="flex flex-col gap-4 md:grid md:grid-cols-2 md:gap-10" aria-busy="true" aria-label="Đang tải sản phẩm">
      <Skeleton className="aspect-square w-full" />
      <div className="flex flex-col gap-3">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}

async function ProductBody({ params }: { params: PageProps<"/san-pham/[slug]">["params"] }) {
  const { slug } = await params;
  const p = await getProduct(slug);
  return (
    <article className="flex flex-col gap-6">
      <JsonLd data={productJsonLd(p)} />
      <div className="flex flex-col gap-5 md:grid md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] md:items-start md:gap-10">
        <Gallery p={p} />
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <PageHeader title={p.name} description={p.subtitle ?? undefined} backHref="/" className="flex-1" />
            {p.seal.total ? <Seal chosen={p.seal.chosen} total={p.seal.total} size={64} className="mt-1" /> : null}
          </div>
          {/* giá hiện một chỗ: máy tính ở đây (khung đặt ngay bên dưới), điện thoại ở khung đặt dính đáy màn hình */}
          <div className="hidden flex-wrap items-center justify-between gap-2 md:flex">
            <div className="flex items-baseline gap-2">
              <Money value={p.price_vnd} className="font-display text-[26px] font-bold" />
              {p.drop && p.price_vnd !== p.list_price_vnd ? <Money value={p.list_price_vnd} strike className="text-[15px]" /> : null}
            </div>
            {p.drop ? (
              <Link href={`/dot/${p.drop.slug}`} className="rounded-md border border-accent px-2.5 py-1 text-[13px] font-medium text-accent">
                Mua chung · {p.drop.label}
              </Link>
            ) : p.stock > 0 ? (
              <Badge tone="success">Có sẵn {p.stock}</Badge>
            ) : (
              <Badge tone="outline">Chờ đợt sau</Badge>
            )}
          </div>
          {p.drop ? <DropNote p={p} /> : null}

          {p.reason_selected.length ? (
            <Card tone="soft">
              <h2 className="text-[17px] font-bold">Vì sao mình chọn</h2>
              <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-[15px]">
                {p.reason_selected.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {p.trial_days ? <p className="mt-2 text-[13px] text-ink-2">Mình dùng thử {p.trial_days} ngày trước khi chọn.</p> : null}
            </Card>
          ) : null}

          {p.not_satisfied ? (
            <Card>
              <h2 className="flex items-center gap-1.5 text-[17px] font-bold">
                <CircleAlert className="size-4 text-seal" aria-hidden /> Điều mình chưa ưng
              </h2>
              <p className="mt-1.5 text-[15px]">{p.not_satisfied}</p>
            </Card>
          ) : null}

          <div className="hidden md:block">
            <BuyBoxFor p={p} showSummary={false} />
          </div>
        </div>
      </div>

      <section aria-labelledby="hoi" className="flex flex-col gap-2">
        <SectionLabel>
          <span id="hoi" className="inline-flex items-center gap-1.5">
            <MessageCircleQuestion className="size-3.5" aria-hidden /> Hỏi về món này
          </span>
        </SectionLabel>
        <AskBox
          productSlug={p.slug}
          productName={p.name}
          pickerName={p.picker_name}
          suggestions={p.faq.length ? [] : ["Món này có điểm gì chưa tốt?", "Thông số chính là gì?"]}
        />
      </section>

      <div className="grid gap-6 md:grid-cols-2 md:gap-10">
        {p.description ? (
          <section aria-labelledby="mo-ta" className="flex flex-col gap-2">
            <SectionLabel>
              <span id="mo-ta">Mô tả</span>
            </SectionLabel>
            <PlainText text={p.description} className="text-[15px] leading-relaxed" />
          </section>
        ) : null}
        {p.specs.length ? (
          <section aria-labelledby="thong-so" className="flex flex-col gap-2">
            <SectionLabel>
              <span id="thong-so">Thông số</span>
            </SectionLabel>
            <Card flush className="px-4">
              <DataList items={p.specs.map((s) => ({ label: s.label, value: s.value }))} />
            </Card>
            {p.shipping_notes.length ? <p className="text-[13px] text-ink-2">Lưu ý: {p.shipping_notes.join(", ")}</p> : null}
          </section>
        ) : null}
      </div>

      {p.faq.length ? (
        <section aria-labelledby="hoi-dap" className="flex flex-col gap-2">
          <SectionLabel>
            <span id="hoi-dap">Hỏi đáp</span>
          </SectionLabel>
          <div className="divide-y divide-line rounded-md border border-line bg-surface">
            {p.faq.map((f) => (
              <details key={f.q} className="group px-4 py-3 [&_summary::-webkit-details-marker]:hidden">
                <summary className="cursor-pointer list-none text-[15px] font-semibold">
                  <span className="mr-2 inline-block text-ink-3 transition-transform group-open:rotate-90">›</span>
                  {f.q}
                </summary>
                <p className="mt-2 text-[15px] text-ink-2">{f.a}</p>
                {f.source ? <p className="mt-1 text-[12.5px] text-ink-3">Nguồn: {f.source}</p> : null}
              </details>
            ))}
          </div>
        </section>
      ) : null}

      <Reviews p={p} />

      {/* Nút đặt luôn trong tầm tay trên điện thoại (ngay trên thanh điều hướng dưới) */}
      <div className="sticky bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+8px)] z-10 rounded-md shadow-[0_6px_24px_-12px_rgb(0_0_0/0.25)] md:hidden">
        <BuyBoxFor p={p} />
      </div>
    </article>
  );
}

function BuyBoxFor({ p, showSummary }: { p: ProductDetail; showSummary?: boolean }) {
  return (
    <BuyBox
      productId={p.id}
      slug={p.slug}
      name={p.name}
      priceVnd={p.drop?.price_vnd || p.price_vnd}
      listPriceVnd={p.drop ? p.list_price_vnd : undefined}
      showSummary={showSummary}
      imageUrl={p.image?.src_small ?? undefined}
      dropId={p.drop?.id}
      dropLabel={p.drop?.label}
      slotsLeft={p.drop ? (p.drop.slots_left ?? undefined) : p.stock}
      available={p.available}
    />
  );
}

function DropNote({ p }: { p: ProductDetail }) {
  const d = p.drop!;
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px] text-ink-2">
      <span className="inline-flex items-center gap-1.5 font-medium text-ink">
        <Hourglass className="size-4" aria-hidden />
        {d.closes_at ? <Countdown until={d.closes_at} /> : d.label}
      </span>
      {d.expected_arrival_date ? <span>Hàng về dự kiến {formatDayMonth(d.expected_arrival_date)}</span> : null}
    </p>
  );
}

function Gallery({ p }: { p: ProductDetail }) {
  if (!p.images.length) {
    // chưa có ảnh: ô giữ chỗ thấp hơn trên điện thoại để tên món và giá không bị đẩy khỏi màn hình đầu
    return <ImageBox alt={p.name} ratio="1/1" placeholder="Ảnh thật, mình tự chụp" className="aspect-[16/9] md:aspect-square" />;
  }
  return (
    <div className="flex flex-col gap-2">
      <ul className="-mx-4 flex snap-x snap-mandatory gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:px-0" aria-label="Ảnh sản phẩm">
        {p.images.map((img, i) => (
          <li key={img.id} className="w-[88%] shrink-0 snap-center md:w-full">
            {/* webp nhẹ hơn jpg ~30%; mọi trình duyệt đang dùng đều đọc được. jpg giữ cho nguồn cấp và Open Graph. */}
            <ImageBox src={img.webp["800"] ?? img.src} alt={img.alt ?? p.name} ratio="1/1" priority={i === 0} />
          </li>
        ))}
      </ul>
      <p className="text-[12.5px] text-ink-3">Ảnh thật, mình tự chụp · {p.images.length} ảnh</p>
    </div>
  );
}

function Reviews({ p }: { p: ProductDetail }) {
  const photos = p.reviews.flatMap((r) => r.photos.map((ph) => ({ ...ph, by: r.display_name })));
  return (
    <section aria-labelledby="danh-gia" className="flex flex-col gap-3">
      <SectionLabel
        aside={p.rating_avg ? <span className="flex items-center gap-1.5 text-[13px] text-ink-2"><Stars value={p.rating_avg} /> {p.rating_avg.toLocaleString("vi-VN")}/5</span> : null}
      >
        <span id="danh-gia">Đánh giá có ảnh · {p.review_count}</span>
      </SectionLabel>
      {photos.length ? (
        <ul className="grid grid-cols-3 gap-2 md:grid-cols-6">
          {photos.slice(0, 6).map((ph, i) => (
            <li key={i}>
              <a href={ph.src ?? undefined} target="_blank" rel="noreferrer" aria-label={`Ảnh của ${ph.by}`}>
                <ImageBox src={ph.thumb} alt={`Ảnh khách ${ph.by} chụp`} ratio="1/1" />
              </a>
            </li>
          ))}
        </ul>
      ) : null}
      {p.reviews.length ? (
        <ul className="flex flex-col divide-y divide-line">
          {p.reviews.map((r) => (
            <li key={r.id} className="py-3 first:pt-0">
              <div className="flex items-center gap-2 text-[14px]">
                <span className="font-semibold">{r.display_name}</span>
                {r.rating ? <Stars value={r.rating} /> : null}
                {r.published_at ? <span className="text-ink-3">{formatDate(r.published_at)}</span> : null}
              </div>
              {r.body ? <p className="mt-1 text-[15px]">{r.body}</p> : null}
              {r.owner_reply ? (
                <p className="mt-2 border-l-2 border-accent pl-3 text-[14px] text-ink-2">
                  <span className="font-semibold text-ink">{ownerReplyLabel(p.picker_name)}:</span> {r.owner_reply}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[14px] text-ink-2">Chưa có đánh giá. Khách nhận hàng sẽ được mời chấm điểm kèm ảnh.</p>
      )}
    </section>
  );
}
