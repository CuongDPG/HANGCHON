import type { PageSection } from "@/components/ui/page-sections";

/**
 * Tầng 1 «tiêu đề là tab» của từng khu desk (xem docs/frontend-guide.md, mục «Ba tầng điều hướng»):
 * các mục lớn, mỗi mục một trang/URL, hiện thẳng trên hàng tiêu đề. Tối đa 5 mục; cấu hình của khu đi sau nút bánh răng.
 */

export const PRODUCT_SECTIONS = [
  { key: "products", href: "/desk/san-pham", label: "Sản phẩm" },
  { key: "drops", href: "/desk/san-pham/dot", label: "Đợt bán" },
  { key: "reviews", href: "/desk/san-pham/danh-gia", label: "Đánh giá" },
  { key: "finds", href: "/desk/san-pham/nho-tim", label: "Nhờ tìm" },
] as const satisfies readonly PageSection[];

export const CONTENT_SECTIONS = [
  { key: "studio", href: "/desk/noi-dung", label: "Xưởng" },
  { key: "calendar", href: "/desk/noi-dung/lich", label: "Lịch đăng" },
  { key: "video", href: "/desk/noi-dung/video", label: "Video" },
  { key: "livestream", href: "/desk/noi-dung/livestream", label: "Livestream" },
  { key: "performance", href: "/desk/noi-dung/so-lieu", label: "Ra đơn" },
] as const satisfies readonly PageSection[];

export const KHACH_SECTIONS = [
  { key: "inbox", href: "/desk/khach", label: "Hộp thư" },
  { key: "book", href: "/desk/khach/so-khach", label: "Sổ khách" },
  { key: "care", href: "/desk/khach/khach-quen", label: "Chăm khách" },
  { key: "trial", href: "/desk/khach/dung-thu", label: "Dùng thử" },
] as const satisfies readonly PageSection[];

/** Tầng 2 của «Chăm khách» (mỗi bước một trang). */
export const KHACH_CARE_TABS = [
  { key: "regulars", href: "/desk/khach/khach-quen", label: "Khách quen" },
  { key: "reorder", href: "/desk/khach/nhac-mua-lai", label: "Nhắc mua lại" },
  { key: "referral", href: "/desk/khach/gioi-thieu", label: "Giới thiệu" },
] as const;

/** Tầng 2 của «Dùng thử»: hai tab của /desk/khach/dung-thu (?tab=) + trang thử hàng. */
export const KHACH_TRIAL_TABS = [
  { key: "offers", href: "/desk/khach/dung-thu", label: "Lời mời" },
  { key: "testers-book", href: "/desk/khach/dung-thu?tab=so", label: "Sổ người thử" },
  { key: "testers", href: "/desk/khach/thu-hang", label: "Thử hàng" },
] as const;

/** Bốn mục sau là tab của /desk/don-hang/van-hanh (?tab=) — giữ nguyên link cũ. */
export const ORDER_SECTIONS = [
  { key: "orders", href: "/desk/don-hang", label: "Đơn" },
  { key: "tien", href: "/desk/don-hang/van-hanh?tab=tien", label: "Tiền về" },
  { key: "doi-tra", href: "/desk/don-hang/van-hanh?tab=doi-tra", label: "Đổi trả" },
  { key: "ton", href: "/desk/don-hang/van-hanh?tab=ton", label: "Tồn kho" },
  { key: "san", href: "/desk/don-hang/van-hanh?tab=san", label: "Sàn" },
] as const satisfies readonly PageSection[];

/** Nguồn cung theo thứ tự công việc; mỗi mục là ?tab= của /desk/nguon-cung (không có tab = Đơn đặt, như cũ). */
export const SUPPLY_SECTIONS = [
  { key: "ncc", href: "/desk/nguon-cung?tab=ncc", label: "Nhà cung cấp" },
  { key: "gia-von", href: "/desk/nguon-cung?tab=gia-von", label: "Giá vốn" },
  { key: "don", href: "/desk/nguon-cung?tab=don", label: "Đơn đặt" },
  { key: "lo-hang", href: "/desk/nguon-cung?tab=lo-hang", label: "Hàng về" },
  { key: "chung-tu", href: "/desk/nguon-cung?tab=chung-tu", label: "Chứng từ" },
] as const satisfies readonly PageSection[];

export const AUTONOMY_SECTIONS = [
  { key: "autonomy", href: "/desk/tu-chu", label: "Mức tự chủ" },
  { key: "costs", href: "/desk/tu-chu/chi-phi-ai", label: "Chi phí AI" },
] as const satisfies readonly PageSection[];

export const AI_LOG_SECTIONS = [
  { key: "ai", href: "/desk/nhat-ky-ai", label: "AI đã làm" },
  { key: "audit", href: "/desk/nhat-ky-ai?tab=luu-vet", label: "Lưu vết duyệt" },
] as const satisfies readonly PageSection[];

export const BOOKS_SECTIONS = [
  { key: "so", href: "/desk/so-sach", label: "Thu chi" },
  { key: "chi-phi", href: "/desk/so-sach?tab=chi-phi", label: "Chi phí" },
  { key: "hoa-don", href: "/desk/so-sach?tab=hoa-don", label: "Hoá đơn" },
] as const satisfies readonly PageSection[];

/** Cấu hình của khu Đơn hàng (nút bánh răng): mẫu tin gửi khách. */
export const ORDER_SETTINGS = { href: "/desk/don-hang/van-hanh?tab=mau-tin", label: "Mẫu tin" };

/** Mục tầng 1 của Đơn hàng kèm số việc cần xem (khoản tiền, yêu cầu đổi trả). */
export function orderSections(c?: { payments_to_review?: number; returns_open?: number }): PageSection[] {
  return ORDER_SECTIONS.map((s) =>
    s.key === "tien" ? { ...s, count: c?.payments_to_review || undefined } : s.key === "doi-tra" ? { ...s, count: c?.returns_open || undefined } : s,
  );
}
