import "server-only";

import { notFound } from "next/navigation";
import { cache } from "react";
import { catalogApi, siteUrl, type ProductDetail } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

/** Lấy sản phẩm một lần cho mỗi request (generateMetadata + trang dùng chung). 404 → trang không tìm thấy. */
export const getProduct = cache(async (slug: string): Promise<ProductDetail> => {
  try {
    return await catalogApi.product(slug);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
});

/** JSON-LD schema.org Product + Offer + AggregateRating + FAQPage (e10). */
export function productJsonLd(p: ProductDetail): Record<string, unknown>[] {
  const url = siteUrl(`/san-pham/${p.slug}`);
  const availability = p.stock > 0 ? "InStock" : p.available ? "PreOrder" : "OutOfStock";
  const product: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Product",
    "@id": `${url}#product`,
    name: p.name,
    url,
    description: p.short_description ?? p.subtitle ?? undefined,
    image: p.images.map((i) => i.src_large ?? i.src).filter(Boolean),
    sku: p.id,
    ...(p.brand ? { brand: { "@type": "Brand", name: p.brand } } : {}),
    ...(p.gtin ? { gtin: p.gtin } : {}),
    ...(p.category ? { category: p.category.name } : {}),
    ...(p.weight_grams ? { weight: { "@type": "QuantitativeValue", value: p.weight_grams, unitCode: "GRM" } } : {}),
    additionalProperty: [
      ...p.specs.map((s) => ({ "@type": "PropertyValue", name: s.label, value: s.value })),
      ...(p.seal.total ? [{ "@type": "PropertyValue", name: "Tỉ lệ chọn", value: `${p.seal.chosen}/${p.seal.total}` }] : []),
      ...(p.trial_days ? [{ "@type": "PropertyValue", name: "Thời gian dùng thử", value: `${p.trial_days} ngày` }] : []),
    ],
    offers: {
      "@type": "Offer",
      url,
      priceCurrency: "VND",
      price: p.price_vnd,
      availability: `https://schema.org/${availability}`,
      itemCondition: "https://schema.org/NewCondition",
      ...(p.drop?.closes_at ? { priceValidUntil: p.drop.closes_at.slice(0, 10) } : {}),
      ...(availability === "PreOrder" && p.drop?.expected_arrival_date ? { availabilityStarts: p.drop.expected_arrival_date } : {}),
      seller: { "@type": "Organization", name: "Hàng Chọn" },
    },
  };
  if (p.review_count > 0 && p.rating_avg) {
    product.aggregateRating = { "@type": "AggregateRating", ratingValue: p.rating_avg, reviewCount: p.review_count, bestRating: 5 };
    product.review = p.reviews.slice(0, 5).map((r) => ({
      "@type": "Review",
      author: { "@type": "Person", name: r.display_name },
      reviewRating: { "@type": "Rating", ratingValue: r.rating, bestRating: 5 },
      ...(r.body ? { reviewBody: r.body } : {}),
      ...(r.published_at ? { datePublished: r.published_at.slice(0, 10) } : {}),
    }));
  }
  const out = [product];
  if (p.faq.length) {
    out.push({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: p.faq.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
    });
  }
  return out;
}
