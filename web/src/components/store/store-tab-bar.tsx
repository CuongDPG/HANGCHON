import { Suspense } from "react";
import { StoreTabBarList, StoreTabBarListActive } from "./store-nav-links";

/** Thanh điều hướng dưới trên điện thoại (ẩn từ md trở lên). */
export function StoreTabBar() {
  return (
    <nav aria-label="Điều hướng" className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface pb-safe md:hidden">
      <Suspense fallback={<StoreTabBarList pathname={null} />}>
        <StoreTabBarListActive />
      </Suspense>
    </nav>
  );
}
