import Link from "next/link";
import { Brand } from "@/components/layout/brand";

// Cùng tên với menu trên (`lib/store-nav.ts`), thêm «Về Hàng Chọn» và «Hỏi trợ lý» (không có trong menu)
const LINKS = [
  { href: "/", label: "Kệ hàng" },
  { href: "/dot", label: "Mua chung" },
  { href: "/nho-tim", label: "Nhờ tìm" },
  { href: "/dung-thu", label: "Dùng thử" },
  { href: "/cua-toi", label: "Của tôi" },
  { href: "/ve-nguoi-chon", label: "Về Hàng Chọn" },
  { href: "/hoi", label: "Hỏi trợ lý" },
];

/** Chân trang website. Thông tin hộ kinh doanh sẽ lấy từ cài đặt khi có (chức năng k1). */
export function StoreFooter() {
  return (
    <footer className="mt-16 border-t border-line bg-surface">
      <div className="mx-auto grid max-w-page gap-8 px-4 py-10 md:grid-cols-[1.4fr_1fr] md:px-6">
        <div>
          <Brand />
          <p className="mt-3 max-w-sm text-[15px] text-ink-2">
            Chọn bằng cả trái tim
          </p>
        </div>
        <nav aria-label="Liên kết chân trang">
          <ul className="grid grid-cols-2 gap-x-6 gap-y-2 text-[15px]">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="text-ink-2 hover:text-ink hover:underline">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
