import type { Metadata } from "next";
import { Suspense } from "react";
import { ReviewForm } from "@/components/catalog/review-form";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import { PageHeader } from "@/components/ui/page-header";
import { catalogApi, type ReviewInvite } from "@/lib/api/catalog";
import { ApiError, errorMessage } from "@/lib/api/client";

export const metadata: Metadata = { title: "Đánh giá món đã nhận", robots: { index: false, follow: false } };

/** Đánh giá có ảnh (e8): link mã một lần gửi cho khách sau khi nhận hàng. */
export default function ReviewPage({ params }: PageProps<"/danh-gia/[token]">) {
  return (
    <div className="flex flex-col gap-5 md:mx-auto md:w-full md:max-w-[36rem]">
      <Suspense fallback={<Skeleton className="h-80 w-full" />}>
        <ReviewBody params={params} />
      </Suspense>
    </div>
  );
}

async function ReviewBody({ params }: { params: PageProps<"/danh-gia/[token]">["params"] }) {
  const { token } = await params;
  let invite: ReviewInvite;
  try {
    invite = await catalogApi.reviewInvite(token);
  } catch (err) {
    const notFound = err instanceof ApiError && err.status === 404;
    return (
      <>
        <PageHeader title="Đánh giá món đã nhận" />
        <EmptyState
          tone={notFound ? "default" : "error"}
          title={notFound ? "Đường link không đúng hoặc đã hết hạn" : "Chưa tải được"}
          description={notFound ? "Bạn mở lại đúng link trong tin nhắn của chị nhé." : errorMessage(err)}
        />
      </>
    );
  }
  return (
    <>
      <PageHeader title="Bạn thấy món này thế nào?" description={invite.product_name} />
      <div className="flex items-center gap-3">
        <div className="w-20 shrink-0">
          <ImageBox src={invite.product_image?.webp["400"] ?? invite.product_image?.src_small} alt={invite.product_name} ratio="1/1" />
        </div>
        <p className="text-[14px] text-ink-2">Đánh giá thật của bạn giúp người mua sau biết món này có hợp với họ không.</p>
      </div>
      <ReviewForm token={token} invite={invite} />
    </>
  );
}
