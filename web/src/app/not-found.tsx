import { SearchX } from "lucide-react";
import Link from "next/link";
import { Brand } from "@/components/layout/brand";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/feedback";

export const metadata = { title: "Không tìm thấy trang" };

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center gap-8 px-4 py-10">
      <Link href="/" className="self-center">
        <Brand />
      </Link>
      <EmptyState
        icon={<SearchX />}
        title="Không tìm thấy trang này"
        description="Đường dẫn có thể đã đổi hoặc món hàng không còn trên kệ."
        action={<ButtonLink href="/">Về kệ hàng</ButtonLink>}
      />
    </main>
  );
}
