import { redirect } from "next/navigation";

/** Cài đặt mở thẳng tab đầu (Cửa hàng, xem `SETTINGS_TABS`); các tab nằm ở thanh dưới tiêu đề mỗi trang. */
export default function DeskSettingsPage() {
  redirect("/desk/cai-dat/cua-hang");
}
