import {
  BarChart3,
  BookOpenText,
  Sunrise,
  ClipboardCheck,
  Factory,
  Gauge,
  History,
  LayoutGrid,
  Megaphone,
  Package,
  ScanSearch,
  Settings,
  Stamp,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

/**
 * Bản đồ route của bàn làm việc — MỘT nguồn duy nhất cho điều hướng dưới, mục «Thêm», cột trái trên máy tính.
 * Đã khai báo đủ mọi khu: agent làm màn hình chỉ cần sửa trang trong `src/app/desk/(app)/<khu>/`,
 * KHÔNG cần sửa file này (trừ khi thêm khu mới hẳn).
 *
 * `features`: mã chức năng trong docs/features.md mà khu này phục vụ.
 */
export type DeskNavItem = {
  key: string;
  href: string;
  label: string;
  /** Mô tả một dòng, hiện ở mục «Thêm» và trang giữ chỗ. */
  description: string;
  icon: LucideIcon;
  features: string[];
};

/** 5 mục điều hướng dưới (điện thoại) / nhóm đầu ở cột trái (máy tính). */
export const DESK_PRIMARY_NAV: DeskNavItem[] = [
  {
    key: "today",
    href: "/desk",
    label: "Hôm nay",
    description: "Việc chờ chị, việc AI đã làm, số đơn, tiền về.",
    icon: Sunrise,
    features: ["i1"],
  },
  {
    key: "sourcing",
    href: "/desk/san-hang",
    label: "Săn hàng",
    description: "Ra đề bằng lời, dán link, tìm bằng ảnh; AI quét nhiều nguồn và thẩm định.",
    icon: ScanSearch,
    features: ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "b1", "b2", "b3", "b4", "b5", "b6", "b7"],
  },
  {
    key: "selection",
    href: "/desk/ban-chon",
    label: "Bàn chọn",
    description: "Ứng viên, mua mẫu, đang thử, đã chọn, đã loại — kèm ghi chú thử hàng.",
    icon: Stamp,
    features: ["c1", "c2", "c3", "c4", "c5", "c6"],
  },
  {
    key: "content",
    href: "/desk/noi-dung",
    label: "Nội dung",
    description: "Bài cho từng kênh, giọng của chị, lịch đăng, soát lời quảng cáo.",
    icon: Megaphone,
    features: ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"],
  },
  {
    key: "customers",
    href: "/desk/khach",
    label: "Khách",
    description: "Hộp thư gộp, sổ khách, nhóm khách quen, nhắc mua lại.",
    icon: UsersRound,
    features: ["h1", "h2", "h3", "h4", "h5", "h6", "h7", "h8"],
  },
];

/** Mục «Thêm» (điện thoại: mở danh sách; máy tính: nhóm sau ở cột trái). */
export const DESK_MORE_NAV: DeskNavItem[] = [
  {
    key: "orders",
    href: "/desk/don-hang",
    label: "Đơn hàng",
    description: "Đợt gom đang mở, đơn theo trạng thái, vận đơn, đổi trả.",
    icon: Package,
    features: ["g1", "g2", "g3", "g4", "g5", "g6", "g7", "g8", "g9"],
  },
  {
    key: "supply",
    href: "/desk/nguon-cung",
    label: "Nguồn cung",
    description: "Nhà cung cấp, giá vốn về tay, đặt mẫu và đặt lô, lô hàng đang về.",
    icon: Factory,
    features: ["d1", "d2", "d3", "d4", "d5", "d6", "d7"],
  },
  {
    key: "approvals",
    href: "/desk/duyet",
    label: "Chờ duyệt",
    description: "Mọi thứ AI làm xong cần chị gật: duyệt, sửa rồi duyệt, trả lại.",
    icon: ClipboardCheck,
    features: ["i2"],
  },
  {
    key: "autonomy",
    href: "/desk/tu-chu",
    label: "Mức tự chủ",
    description: "Việc nào AI tự làm, việc nào phải hỏi chị; trần chi phí AI.",
    icon: Gauge,
    features: ["i3", "k2"],
  },
  {
    key: "ai-log",
    href: "/desk/nhat-ky-ai",
    label: "Nhật ký AI",
    description: "AI đã làm gì, dựa vào đâu; hoàn tác được.",
    icon: History,
    features: ["i4", "k3"],
  },
  {
    key: "reports",
    href: "/desk/bao-cao",
    label: "Báo cáo",
    description: "Báo cáo tuần: doanh thu, biên lợi nhuận, khách quay lại, bài hiệu quả.",
    icon: BarChart3,
    features: ["i5", "f7"],
  },
  {
    key: "books",
    href: "/desk/so-sach",
    label: "Sổ sách",
    description: "Sổ doanh thu, chi phí, bảng kê khai thuế, hoá đơn điện tử.",
    icon: BookOpenText,
    features: ["k1", "k5"],
  },
  {
    key: "products",
    href: "/desk/san-pham",
    label: "Sản phẩm",
    description: "Trang sản phẩm trên website, đợt mở bán, tồn kho nhỏ, đánh giá.",
    icon: LayoutGrid,
    features: ["e1", "e2", "e3", "e6", "e8", "e9", "e10", "g8"],
  },
  {
    key: "settings",
    href: "/desk/cai-dat",
    label: "Cài đặt",
    description: "Tài khoản, người phụ giúp, kênh bán, giao diện, sao lưu.",
    icon: Settings,
    features: ["k4"],
  },
];

export const DESK_NAV: DeskNavItem[] = [...DESK_PRIMARY_NAV, ...DESK_MORE_NAV];

/** Trang ngoài khung (không cần đăng nhập / không có điều hướng). */
export const DESK_PUBLIC_ROUTES = {
  login: "/desk/dang-nhap",
  kit: "/desk/kit",
} as const;

/** Mục điều hướng ứng với đường dẫn hiện tại (khớp tiền tố dài nhất; `/desk` chỉ khớp đúng). */
export function findDeskNav(pathname: string): DeskNavItem | undefined {
  let best: DeskNavItem | undefined;
  for (const item of DESK_NAV) {
    const hit = item.href === "/desk" ? pathname === "/desk" : pathname === item.href || pathname.startsWith(`${item.href}/`);
    if (hit && (!best || item.href.length > best.href.length)) best = item;
  }
  return best;
}
