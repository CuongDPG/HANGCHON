import type { Metadata } from "next";
import { Suspense } from "react";
import { AskBox } from "@/components/assistant/ask-box";
import { Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { catalogApi } from "@/lib/api/catalog";

export const metadata: Metadata = {
  title: "Hỏi trợ lý",
  description: "Trợ lý AI trả lời từ hồ sơ thẩm định của người chọn, có dẫn nguồn. Không biết thì chuyển cho chị.",
  alternates: { canonical: "/hoi" },
};

const SUGGESTIONS = ["Có bình giữ nhiệt nào nhẹ không?", "Món nào dùng được cho bé?", "Đợt này bao giờ hàng về?"];

/** Hỏi trợ lý (e7). `?mon=<slug>` → hỏi về đúng một món. */
export default function AskPage({ searchParams }: PageProps<"/hoi">) {
  return (
    <div className="flex flex-col gap-5">
      <Suspense fallback={<PageHeader title="Hỏi trợ lý" />}>
        <AskBody searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function AskBody({ searchParams }: { searchParams: PageProps<"/hoi">["searchParams"] }) {
  const sp = await searchParams;
  const slug = typeof sp.mon === "string" ? sp.mon : null;
  let name: string | null = null;
  if (slug) {
    try {
      name = (await catalogApi.product(slug)).name;
    } catch {
      name = null;
    }
  }
  return (
    <>
      <PageHeader
        title={name ? `Hỏi về ${name}` : "Hỏi trợ lý"}
        description="Trợ lý trả lời từ hồ sơ của chị: mô tả, thông số, ghi chú thử hàng. Câu nào chưa có dữ liệu sẽ được chuyển cho chị."
        backHref={name && slug ? `/san-pham/${slug}` : undefined}
      />
      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <AskBox productSlug={name ? slug : null} productName={name} suggestions={name ? [] : SUGGESTIONS} />
      </Suspense>
    </>
  );
}
