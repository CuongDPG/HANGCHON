import { MessagesSquare } from "lucide-react";
import { StorePlaceholder } from "@/components/store/store-placeholder";

export const metadata = { title: "Hỏi trợ lý" };

/** Hỏi trợ lý (e7): AI trả lời từ hồ sơ thẩm định, có dẫn nguồn; không biết thì chuyển chị. */
export default function AssistantPage() {
  return (
    <StorePlaceholder
      title="Hỏi trợ lý"
      description="Trợ lý là AI, trả lời dựa trên hồ sơ thẩm định. Câu nào chưa chắc sẽ được chuyển cho chị."
      icon={<MessagesSquare />}
      emptyTitle="Trợ lý chưa sẵn sàng"
      emptyDescription="Khi có món trên kệ, bạn hỏi về món nào trợ lý sẽ trả lời kèm nguồn."
    />
  );
}
