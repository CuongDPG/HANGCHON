import { StoreFooter } from "@/components/store/store-footer";
import { StoreHeader } from "@/components/store/store-header";
import { StoreTabBar } from "@/components/store/store-tab-bar";

/** Khung website cho khách: đầu trang, nội dung, chân trang, thanh dưới (điện thoại). */
export default function StoreLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <StoreHeader />
      <main id="noi-dung" className="mx-auto w-full max-w-page px-4 pt-5 md:px-6 md:pt-10">
        {children}
      </main>
      <StoreFooter />
      {/* Chừa chỗ cho thanh điều hướng dưới trên điện thoại */}
      <div aria-hidden className="h-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px))] md:hidden" />
      <StoreTabBar />
    </>
  );
}
