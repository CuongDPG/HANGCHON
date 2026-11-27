import { FlaskConical, Hourglass, LayoutGrid, Package, Search, UserRound, type LucideIcon } from "lucide-react";

/** Điều hướng website cho khách: thanh dưới trên điện thoại, hàng menu trên đầu trang trên máy tính. */
export type StoreNavItem = { href: string; label: string; icon: LucideIcon };

export const STORE_NAV: StoreNavItem[] = [
  { href: "/", label: "Kệ hàng", icon: LayoutGrid },
  { href: "/dot", label: "Mua chung", icon: Hourglass },
  { href: "/nho-tim", label: "Nhờ tìm", icon: Search },
  { href: "/dung-thu", label: "Dùng thử", icon: FlaskConical },
  { href: "/don", label: "Đơn", icon: Package },
  { href: "/ve-nguoi-chon", label: "Người chọn", icon: UserRound },
];

/** Mục đang chọn: "/" chỉ khớp trang chủ và trang sản phẩm (nằm trên kệ). */
export function isStoreNavActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/san-pham");
  return pathname === href || pathname.startsWith(`${href}/`);
}
