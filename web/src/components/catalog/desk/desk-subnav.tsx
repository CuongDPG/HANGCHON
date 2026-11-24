import Link from "next/link";
import { cn } from "@/lib/cn";

const ITEMS = [
  { key: "products", href: "/desk/san-pham", label: "Sản phẩm" },
  { key: "drops", href: "/desk/san-pham/dot", label: "Đợt bán" },
  { key: "reviews", href: "/desk/san-pham/danh-gia", label: "Đánh giá" },
  { key: "finds", href: "/desk/san-pham/nho-tim", label: "Nhờ tìm" },
] as const;

export type SubnavKey = (typeof ITEMS)[number]["key"];

/** Thanh phụ của khu Sản phẩm: Sản phẩm · Đợt bán · Đánh giá · Nhờ tìm. */
export function DeskSubnav({ active }: { active: SubnavKey }) {
  return (
    <nav aria-label="Khu sản phẩm" className="-mx-4 flex gap-1 overflow-x-auto border-b border-line px-4 [scrollbar-width:none] md:mx-0 md:px-0">
      {ITEMS.map((i) => (
        <Link
          key={i.key}
          href={i.href}
          aria-current={active === i.key ? "page" : undefined}
          className={cn(
            "-mb-px shrink-0 border-b-2 px-3 py-2.5 text-[15px] whitespace-nowrap",
            active === i.key ? "border-accent font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink",
          )}
        >
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
