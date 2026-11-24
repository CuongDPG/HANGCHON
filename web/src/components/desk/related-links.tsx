import Link from "next/link";

export type RelatedLink = { href: string; label: string } | null | false | "" | undefined;

/** Hàng liên kết sang màn hình liên quan (ứng viên ↔ hồ sơ ↔ giá vốn ↔ sản phẩm ↔ nội dung). */
export function RelatedLinks({ links }: { links: RelatedLink[] }) {
  const items = links.filter(Boolean) as { href: string; label: string }[];
  if (!items.length) return null;
  return (
    <nav aria-label="Màn hình liên quan" className="-mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[14px]">
      {items.map((l) => (
        <Link key={l.href} href={l.href} className="font-semibold text-accent">
          {l.label} →
        </Link>
      ))}
    </nav>
  );
}
