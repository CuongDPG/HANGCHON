import type { Metadata } from "next";
import { Suspense } from "react";
import { FindBoard } from "@/components/catalog/find-board";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import type { FindRequestsPage } from "@/lib/api/catalog";
import { errorMessage } from "@/lib/api/client";
import { serverFetch } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Nhờ tìm",
  description: "Bạn cần món gì mà chưa tìm được loại ưng? Gửi nhu cầu, người khác bấm «mình cũng cần». Đủ người, mình mở tìm.",
  alternates: { canonical: "/nho-tim" },
};

/** Nhờ tìm (e9). Danh sách đọc kèm cookie thiết bị để biết bạn đã bấm «cùng cần» món nào. */
export default function FindPage({ searchParams }: PageProps<"/nho-tim">) {
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Bạn cần món gì mà chưa tìm được loại ưng?" description="Người khác cũng cần thì bấm «mình cũng cần». Đây là cộng đồng." />
      <Suspense fallback={<SkeletonList rows={4} />}>
        <FindBody searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function FindBody({ searchParams }: { searchParams: PageProps<"/nho-tim">["searchParams"] }) {
  const sp = await searchParams;
  const prefill = typeof sp.tim === "string" ? sp.tim.slice(0, 200) : undefined;
  let data: FindRequestsPage;
  try {
    data = await serverFetch<FindRequestsPage>("/api/store/catalog/finds");
  } catch (err) {
    return <EmptyState tone="error" title="Chưa tải được danh sách" description={errorMessage(err)} />;
  }
  return <FindBoard initial={data.items} threshold={data.threshold} prefill={prefill} />;
}
