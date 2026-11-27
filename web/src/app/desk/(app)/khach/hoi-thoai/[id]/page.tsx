import { Suspense } from "react";
import { ConversationScreen } from "@/components/inbox/conversation-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Hội thoại" };

/** Một hội thoại trong hộp thư (h1–h3). Đọc params là dữ liệu theo request → đặt trong <Suspense>. */
export default function ConversationPage({ params }: PageProps<"/desk/khach/hoi-thoai/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/khach" />}>
      <Conversation params={params} />
    </Suspense>
  );
}

async function Conversation({ params }: { params: PageProps<"/desk/khach/hoi-thoai/[id]">["params"] }) {
  const { id } = await params;
  return <ConversationScreen id={id} />;
}
