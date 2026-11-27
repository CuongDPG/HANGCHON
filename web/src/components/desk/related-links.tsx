import { ArrowRight } from "lucide-react";
import type { DeskMoreItem } from "./desk-more-menu";

export type RelatedLink = { href: string; label: string } | null | false | "" | undefined;

/** Liên kết sang màn liên quan (ứng viên ↔ hồ sơ ↔ giá vốn ↔ sản phẩm ↔ nội dung) → mục của menu «⋯» (DeskMoreMenu). */
export function relatedItems(links: RelatedLink[]): DeskMoreItem[] {
  return (links.filter(Boolean) as { href: string; label: string }[]).map((l) => ({ href: l.href, label: l.label, icon: <ArrowRight aria-hidden /> }));
}
