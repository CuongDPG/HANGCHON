import { UserRound } from "lucide-react";
import { StorePlaceholder } from "@/components/store/store-placeholder";

export const metadata = { title: "Về người chọn" };

/** Về người chọn: chị là ai, chọn theo nguyên tắc nào, AI giúp việc gì. */
export default function AboutPage() {
  return (
    <StorePlaceholder
      title="Về người chọn"
      icon={<UserRound />}
      emptyTitle="Trang giới thiệu đang được viết"
      emptyDescription="Ở đây sẽ có cách chọn hàng, những món không bán, và việc AI giúp. Quyết định chọn là của người."
    />
  );
}
