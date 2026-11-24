import type { Metadata } from "next";

/**
 * Bàn làm việc: PWA riêng (manifest phạm vi /desk), không cho máy tìm kiếm lập chỉ mục.
 * Icon: app/icon.svg (trình duyệt), app/apple-icon.png (màn hình chính iOS), public/desk/icon-*.png (manifest).
 */
export const metadata: Metadata = {
  title: { default: "Bàn làm việc", template: "%s · Bàn làm việc · Hàng Chọn" },
  manifest: "/desk/manifest.webmanifest",
  robots: { index: false, follow: false },
  appleWebApp: { capable: true, title: "Hàng Chọn", statusBarStyle: "default" },
};

export default function DeskRootLayout({ children }: LayoutProps<"/desk">) {
  return children;
}
