import type { Metadata, Viewport } from "next";
import { Providers } from "@/components/providers";
import { THEME_SCRIPT } from "@/lib/theme";
import { beVietnam, bricolage } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Hàng Chọn · Mỗi món đều đã được chọn và dùng thử",
    template: "%s · Hàng Chọn",
  },
  description:
    "Đồ gia dụng nhỏ được chọn kỹ: mua mẫu, dùng thật ít nhất hai tuần, nói rõ cả điều chưa ưng. Mở bán theo đợt.",
  applicationName: "Hàng Chọn",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f6f2" },
    { media: "(prefers-color-scheme: dark)", color: "#121318" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className={`${beVietnam.variable} ${bricolage.variable} antialiased`} suppressHydrationWarning>
      <head>
        {/* Đặt giao diện sáng/tối đã chọn trước khi vẽ trang, tránh nháy màu */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
