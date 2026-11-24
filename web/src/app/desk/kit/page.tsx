import { KitShowcase } from "./kit-showcase";

export const metadata = { title: "Bộ giao diện" };

/**
 * Trang trưng bày hệ thiết kế «Chàm»: mọi token và component, sáng/tối. Không cần đăng nhập, không gọi API.
 * Thêm component mới vào components/ui thì bày thêm một khối ở kit-showcase.tsx.
 */
export default function KitPage() {
  return <KitShowcase />;
}
