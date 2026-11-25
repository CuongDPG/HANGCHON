import Link from "next/link";
import { Brand } from "@/components/layout/brand";

const LINKS = [
  { href: "/ve-nguoi-chon", label: "Về người chọn" },
  { href: "/dot", label: "Đợt gom đơn" },
  { href: "/nho-tim", label: "Nhờ chị tìm" },
  { href: "/don", label: "Tra cứu đơn" },
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
