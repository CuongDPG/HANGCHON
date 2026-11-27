"use client";

import { Eye, EyeOff, MessageSquareReply, ShieldAlert, Star } from "lucide-react";
import { useState } from "react";
import { Stars } from "@/components/catalog/stars";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Textarea } from "@/components/ui/field";
import { ImageBox } from "@/components/ui/image-box";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { notifySuccess } from "@/components/ui/toast";
import { useSession } from "@/lib/api/auth";
import {
  useDeskReviews,
  useReplyReview,
  useReviewAction,
  useReviewReasonVisibility,
  type DeskReview,
  type ReviewStatus,
} from "@/lib/api/catalog";
import { formatDate } from "@/lib/format";
import { DeskSubnav } from "./desk-subnav";

const FLAG_LABELS: Record<string, string> = { spam: "Quảng cáo / spam", offensive: "Thô tục", personal_info: "Lộ thông tin cá nhân", off_topic: "Lạc đề" };

/** Đánh giá chờ duyệt (e8): AI lọc trước, chị quyết định hiện hay không. Chê thật lòng vẫn nên hiện. */
export function ReviewsScreen() {
  const [tab, setTab] = useState<ReviewStatus>("pending_review");
  const { data, isPending, error } = useDeskReviews(tab);
  const rows = data?.items ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Đánh giá của khách" />
      <DeskSubnav active="reviews" />
      <Tabs
        aria-label="Trạng thái đánh giá"
        value={tab}
        onChange={setTab}
        items={[
          { value: "pending_review", label: "Chờ duyệt" },
          { value: "published", label: "Đang hiện" },
          { value: "hidden", label: "Đã ẩn" },
          { value: "rejected", label: "Không hiện" },
        ]}
      />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được đánh giá" description={error.message} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<Star />} title="Không có đánh giá nào ở mục này" />
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((r) => (
            <li key={r.id}>
              <ReviewCard r={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewCard({ r }: { r: DeskReview }) {
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const act = useReviewAction();
  const reply = useReplyReview();
  const reasonVis = useReviewReasonVisibility();
  const [text, setText] = useState(r.owner_reply ?? "");
  const flags = Object.entries(FLAG_LABELS).filter(([k]) => r.ai_flags[k as keyof DeskReview["ai_flags"]]);
  const hide = r.ai_flags.recommend === "hide";
  return (
    <Card tone={hide && r.status === "pending_review" ? "danger" : "default"} className="flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-semibold">{r.product_name}</p>
          <p className="flex items-center gap-2 text-[13px] text-ink-2">
            {r.rating ? <Stars value={r.rating} /> : null}
            {r.display_name ?? "Khách"}
            {r.submitted_at ? ` · ${formatDate(r.submitted_at)}` : ""}
          </p>
        </div>
        {r.status === "pending_review" ? <Badge tone={hide ? "danger" : "success"}>{hide ? "AI đề xuất ẩn" : "AI đề xuất hiện"}</Badge> : null}
      </div>
      {r.body ? <p className="text-[15px]">{r.body}</p> : <p className="text-[14px] text-ink-3">(Không viết chữ)</p>}
      {r.choice_reason ? (
        <div className="flex flex-col gap-1.5 rounded-md bg-soft px-3 py-2">
          <p className="text-[13px] text-ink-2">
            Vì sao khách chọn
            {r.reason_public ? null : <span className="text-ink-3"> · đang ẩn trên website</span>}
          </p>
          <p className={r.reason_public ? "text-[15px]" : "text-[15px] text-ink-3 line-through"}>{r.choice_reason}</p>
          {isOwner ? (
            <Button size="sm" variant="ghost" className="self-start" icon={r.reason_public ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              loading={reasonVis.isPending}
              onClick={() => reasonVis.mutate({ id: r.id, visible: !r.reason_public },
                { onSuccess: () => notifySuccess(r.reason_public ? "Đã ẩn lý do chọn, đánh giá vẫn giữ" : "Đã hiện lại lý do chọn") })}>
              {r.reason_public ? "Ẩn lý do này" : "Hiện lý do này"}
            </Button>
          ) : null}
        </div>
      ) : null}
      {r.photo_urls.length ? (
        <div className="grid grid-cols-4 gap-2">
          {r.photo_urls.map((u, i) => (
            <ImageBox key={i} src={u} alt={`Ảnh khách gửi ${i + 1}`} ratio="1/1" />
          ))}
        </div>
      ) : null}
      {flags.length || r.ai_summary ? (
        <p className="flex items-start gap-1.5 text-[13px] text-ink-2">
          <ShieldAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            {flags.length ? `${flags.map(([, l]) => l).join(", ")}. ` : ""}
            {r.ai_summary}
          </span>
        </p>
      ) : null}
      {isOwner ? (
        <div className="flex flex-wrap gap-2">
          {r.status !== "published" ? (
            <Button size="sm" icon={<Eye className="size-4" />} loading={act.isPending && act.variables?.action === "approve"}
              onClick={() => act.mutate({ id: r.id, action: "approve" }, { onSuccess: () => notifySuccess("Đã hiện trên trang sản phẩm") })}>
              Hiện
            </Button>
          ) : null}
          {r.status === "pending_review" || r.status === "published" ? (
            <Button size="sm" variant="secondary" icon={<EyeOff className="size-4" />} loading={act.isPending && act.variables?.action === "reject"}
              onClick={() => act.mutate({ id: r.id, action: "reject" }, { onSuccess: () => notifySuccess("Đã ẩn") })}>
              {r.status === "published" ? "Ẩn" : "Không hiện"}
            </Button>
          ) : null}
        </div>
      ) : null}
      {isOwner && r.status === "published" ? (
        <div className="flex flex-col gap-2">
          <Textarea aria-label="Chị trả lời" placeholder="Chị trả lời công khai (không bắt buộc)" value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={1000} />
          <Button size="sm" variant="ghost" icon={<MessageSquareReply className="size-4" />} className="self-start" loading={reply.isPending}
            disabled={text === (r.owner_reply ?? "")} onClick={() => reply.mutate({ id: r.id, reply: text }, { onSuccess: () => notifySuccess("Đã lưu câu trả lời") })}>
            Lưu câu trả lời
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
