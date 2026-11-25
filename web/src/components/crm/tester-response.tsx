"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, FlaskConical, Star } from "lucide-react";
import { useState } from "react";
import { Button, Card, EmptyState, ImageBox, PageHeader, SkeletonList, Textarea } from "@/components/ui";
import { publicInviteApi, type PublicInvite } from "@/lib/api/crm";
import { cn } from "@/lib/cn";

/** Trang khách mở từ link mời thử hàng (h8): nhận thử / không nhận, rồi gửi cảm nhận một lần. Gọi khách là «bạn». */
export function TesterResponse({ token }: { token: string }) {
  const key = ["store", "tester-invite", token];
  const qc = useQueryClient();
  const { data, isPending, error } = useQuery({ queryKey: key, queryFn: () => publicInviteApi.get(token) });
  const respond = useMutation({
    mutationFn: (body: Parameters<typeof publicInviteApi.respond>[1]) => publicInviteApi.respond(token, body),
    meta: { silentError: true },
    onSuccess: (d) => qc.setQueryData(key, d),
  });
  const [feedback, setFeedback] = useState("");
  const [rating, setRating] = useState<number | null>(null);

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Thử hàng cùng mình" />
        <SkeletonList rows={2} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Thử hàng cùng mình" />
        <EmptyState tone="error" icon={<FlaskConical />} title="Link này không còn dùng được" description="Có thể lời mời đã đóng. Bạn nhắn mình qua Zalo hoặc Facebook nhé." />
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader eyebrow={`Chào ${data.first_name}`} title="Thử hàng cùng mình" />
      <Card className="flex items-start gap-3">
        <ImageBox src={data.image_url} alt={data.product_title} ratio="1/1" className="w-20 shrink-0" placeholder="Ảnh" />
        <div className="min-w-0">
          <h2 className="text-[17px] leading-snug font-semibold">{data.product_title}</h2>
          {data.message ? <p className="mt-1 text-[14.5px] text-ink-2 [text-wrap:pretty]">{data.message}</p> : null}
        </div>
      </Card>
      <Body
        data={data}
        loading={respond.isPending}
        error={respond.error?.message}
        feedback={feedback}
        setFeedback={setFeedback}
        rating={rating}
        setRating={setRating}
        onAnswer={(accept) => respond.mutate({ action: accept ? "accept" : "decline" })}
        onFeedback={() => respond.mutate({ action: "feedback", feedback, rating })}
      />
    </div>
  );
}

function Body(props: {
  data: PublicInvite;
  loading: boolean;
  error?: string;
  feedback: string;
  setFeedback: (v: string) => void;
  rating: number | null;
  setRating: (v: number) => void;
  onAnswer: (accept: boolean) => void;
  onFeedback: () => void;
}) {
  const { data } = props;
  if (data.status === "feedback_received") {
    return (
      <EmptyState
        icon={<CircleCheck />}
        title="Cảm ơn bạn đã kể thật lòng!"
        description="Mình đọc kỹ từng dòng trước khi quyết định có bán món này không. Cảm nhận chỉ gửi được một lần."
      />
    );
  }
  if (data.status === "declined") {
    return <EmptyState title="Không sao cả" description="Lần sau có món mới mình lại hỏi bạn nhé." />;
  }
  return (
    <div className="flex flex-col gap-4">
      {data.can_answer ? (
        <Card tone="soft" className="flex flex-col gap-3">
          <p className="text-[15px]">Bạn có muốn nhận mẫu dùng thử không? Mình gửi tận nơi, không mất phí.</p>
          <div className="flex gap-2">
            <Button loading={props.loading} onClick={() => props.onAnswer(true)}>
              Mình nhận thử
            </Button>
            <Button variant="secondary" disabled={props.loading} onClick={() => props.onAnswer(false)}>
              Lần này thôi
            </Button>
          </div>
        </Card>
      ) : null}
      {data.can_feedback ? (
        <Card className="flex flex-col gap-3">
          <h2 className="text-[17px] font-semibold">Dùng xong rồi? Kể mình nghe</h2>
          <div role="radiogroup" aria-label="Chấm điểm" className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                role="radio"
                aria-checked={props.rating === n}
                aria-label={`${n} sao`}
                onClick={() => props.setRating(n)}
                className={cn("rounded-md p-1.5", (props.rating ?? 0) >= n ? "text-review" : "text-ink-3")}
              >
                <Star className="size-7" aria-hidden fill={(props.rating ?? 0) >= n ? "currentColor" : "none"} />
              </button>
            ))}
          </div>
          <Textarea
            label="Bạn thấy món này thế nào?"
            hint="Điều thích, điều chưa ưng, có muốn mua không. Viết thật lòng giúp mình nhé."
            value={props.feedback}
            onChange={(e) => props.setFeedback(e.target.value)}
            rows={4}
            error={props.error}
          />
          <Button loading={props.loading} disabled={!props.feedback.trim()} onClick={props.onFeedback} className="self-start">
            Gửi cảm nhận
          </Button>
        </Card>
      ) : null}
    </div>
  );
}
