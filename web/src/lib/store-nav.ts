import { FlaskConical, Hourglass, LayoutGrid, Search, ShoppingCart, type LucideIcon } from "lucide-react";

/** Điều hướng website cho khách: thanh dưới trên điện thoại, hàng menu trên đầu trang trên máy tính. */
export type StoreNavItem = { href: string; label: string; icon: LucideIcon; /** Hiện số món trong giỏ. */ cartCount?: boolean };

export const STORE_NAV: StoreNavItem[] = [
  { href: "/", label: "Kệ hàng", icon: LayoutGrid },
  { href: "/dot", label: "Mua chung", icon: Hourglass },
  { href: "/nho-tim", label: "Nhờ tìm", icon: Search },
  { href: "/dung-thu", label: "Dùng thử", icon: FlaskConical },
  { href: "/cua-toi", label: "Của tôi", icon: ShoppingCart, cartCount: true },
];

/** Mục đang chọn: "/" chỉ khớp trang chủ và trang sản phẩm (nằm trên kệ); «Của tôi» sáng cả ở đặt hàng, theo dõi đơn. */
export function isStoreNavActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/san-pham");
  if (href === "/cua-toi" && (pathname === "/dat-hang" || pathname.startsWith("/don/"))) return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}
