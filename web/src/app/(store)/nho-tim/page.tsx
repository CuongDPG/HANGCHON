import { HandHelping } from "lucide-react";
import { StorePlaceholder } from "@/components/store/store-placeholder";

export const metadata = { title: "Nhờ chị tìm" };

/** Nhờ chị tìm (e9): khách gửi nhu cầu, người khác bấm «mình cũng cần». */
export default function FindRequestsPage() {
  return (
    <StorePlaceholder
      title="Nhờ chị tìm"
      description="Bạn cần món gì mà chưa tìm được loại ưng? Món nào đủ nhiều người cùng cần, chị sẽ mở tìm."
      icon={<HandHelping />}
      emptyTitle="Chưa có lời nhờ nào"
      emptyDescription="Ô gửi lời nhờ và danh sách «mình cũng cần» sẽ hiện ở đây."
    />
  );
}
