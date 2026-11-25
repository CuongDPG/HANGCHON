import Link from "next/link";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { Seal } from "@/components/ui/seal";
import type { ProductCard as Card } from "@/lib/api/catalog";

/**
 * Thẻ món trên kệ (hướng B): ảnh vuông + con dấu, tên, giá, rồi bằng chứng đã thử («Thử 3 tuần · Nhật»)
 * đứng đúng chỗ sàn khác đặt số sao.
 */
export function ProductCard({ product, priority = false }: { product: Card; priority?: boolean }) {
  const p = product;
  return (
    <Link href={`/san-pham/${p.slug}`} className="group flex min-w-0 flex-col gap-1.5" prefetch={false}>
      <ImageBox
        src={p.image?.webp["400"] ?? p.image?.src_small ?? p.image?.src}
        alt={p.name}
        ratio="1/1"
        priority={priority}
        placeholder="Ảnh mình tự chụp"
        imgClassName="transition-transform duration-300 group-hover:scale-[1.02]"
        overlay={p.seal.total ? <Seal chosen={p.seal.chosen} total={p.seal.total} size={46} /> : <Seal size={46} />}
      />
      <span className="mt-1 line-clamp-2 text-[15px] leading-snug font-semibold [text-wrap:pretty] group-hover:underline">
        {p.name}
      </span>
      <span className="flex flex-wrap items-baseline gap-x-2">
        <Money value={p.price_vnd} className="text-[15px]" />
        {p.drop && p.price_vnd !== p.list_price_vnd ? <Money value={p.list_price_vnd} strike className="text-[13px]" /> : null}
      </span>
      {p.proof ? <span className="text-[13px] text-ink-2">{p.proof}</span> : null}
      {p.drop ? (
        <span className="text-[12.5px] font-medium text-accent">
          Mua chung · {p.drop.label}
          {p.drop.slots_left !== null ? ` · còn ${p.drop.slots_left} suất` : ""}
        </span>
      ) : null}
    </Link>
  );
}
