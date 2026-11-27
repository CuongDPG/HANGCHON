"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CircleCheck, FlaskConical, Star, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Card, DateTime, EmptyState, ImageBox, Input, Money, PageHeader, RadioGroup, SkeletonList, Textarea } from "@/components/ui";
import { WOULD_BUY_LABEL, publicCotrialApi, publicInviteApi, type PublicInvite } from "@/lib/api/crm";
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
      {data.cotrial ? (
        <CotrialBody token={token} data={data} onDone={(d) => qc.setQueryData(key, d)} />
      ) : (
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
      )}
    </div>
  );
}

const MAX_PHOTOS = 3;

/** «Mời thử cùng»: trạng thái của người đăng ký + form cảm nhận có cấu trúc (gửi một lần, đủ thì được hoàn tiền). */
function CotrialBody({ token, data, onDone }: { token: string; data: PublicInvite; onDone: (d: PublicInvite) => void }) {
  const c = data.cotrial!;
  const [rating, setRating] = useState(0);
  const [liked, setLiked] = useState("");
  const [disliked, setDisliked] = useState("");
  const [wouldBuy, setWouldBuy] = useState<"" | keyof typeof WOULD_BUY_LABEL>("");
  const [account, setAccount] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const send = useMutation({
    mutationFn: (form: FormData) => publicCotrialApi.feedback(token, form),
    meta: { silentError: true },
    onSuccess: onDone,
  });
  const status: Partial<Record<PublicInvite["status"], [string, string]>> = {
    applied: ["Mình đã nhận đăng ký", "Chọn xong người thử, mình nhắn riêng cho bạn nhé."],
    declined: ["Lần này mình chưa mời bạn", "Món sau có dịp mình lại mời bạn nhé. Cảm ơn bạn đã đăng ký!"],
    selected: ["Bạn được chọn dùng thử", "Bạn chuyển khoản theo hướng dẫn mình nhắn riêng; nhận tiền xong mình gửi hàng ngay."],
    paid: ["Mình đã nhận tiền", "Mình sắp gửi hàng. Nhận hàng rồi bạn quay lại link này để gửi cảm nhận."],
    feedback_received: ["Cảm ơn bạn đã kể thật lòng!", "Mình sẽ chuyển hoàn tiền cho bạn trong vài ngày."],
    refund_proposed: ["Cảm ơn bạn đã kể thật lòng!", "Mình sẽ chuyển hoàn tiền cho bạn trong vài ngày."],
    refunded: ["Mình đã hoàn tiền", "Cảm ơn bạn đã dùng thử cùng mình."],
    feedback_missed: ["Đã quá hạn gửi cảm nhận", "Lần này mình không hoàn tiền được, mong bạn thông cảm."],
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    const form = new FormData();
    form.append("rating", String(rating));
    form.append("liked", liked.trim());
    form.append("disliked", disliked.trim());
    form.append("would_buy", wouldBuy);
    if (account.trim()) form.append("refund_account", account.trim());
    files.forEach((f) => form.append("photos", f));
    await send.mutateAsync(form).catch(() => null);
  }

  const terms = (
    <p className="text-[14.5px]">
      Giá <Money value={c.price_vnd} /> · gửi cảm nhận đủ {c.feedback_due_at ? (
        <>
          trước ngày <DateTime value={c.feedback_due_at} format="date" />
        </>
      ) : (
        <>trong {c.feedback_days} ngày sau khi nhận hàng</>
      )}{" "}
      được hoàn <Money value={c.refund_vnd} />.
    </p>
  );
  const s = status[data.status];
  if (!data.can_feedback) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState icon={<CircleCheck />} title={s?.[0] ?? "Lời mời dùng thử"} description={s?.[1]} />
        {terms}
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Card tone="soft">{terms}</Card>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[15px] font-semibold">Bạn chấm mấy sao?</legend>
        <div role="radiogroup" aria-label="Chấm điểm" className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={rating === n}
              aria-label={`${n} sao`}
              onClick={() => setRating(n)}
              className={cn("rounded-md p-1.5", rating >= n ? "text-review" : "text-ink-3")}
            >
              <Star className="size-7" aria-hidden fill={rating >= n ? "currentColor" : "none"} />
            </button>
          ))}
        </div>
      </fieldset>
      <Textarea label="Bạn thích điều gì?" rows={3} value={liked} onChange={(e) => setLiked(e.target.value)} maxLength={2000} />
      <Textarea label="Điều gì bạn chưa ưng?" hint="Chưa thấy gì thì ghi «chưa thấy»." rows={3} value={disliked} onChange={(e) => setDisliked(e.target.value)} maxLength={2000} />
      <RadioGroup
        name="would_buy"
        legend={`Nếu giá ${c.ask_price_vnd.toLocaleString("vi-VN")}đ, bạn có mua không?`}
        value={wouldBuy || null}
        onChange={setWouldBuy}
        options={(Object.keys(WOULD_BUY_LABEL) as (keyof typeof WOULD_BUY_LABEL)[]).map((k) => ({ value: k, label: WOULD_BUY_LABEL[k] }))}
      />
      <div className="flex flex-col gap-2">
        <span className="text-[15px] font-semibold">Ảnh lúc dùng (không bắt buộc, tối đa {MAX_PHOTOS})</span>
        <div className="flex flex-wrap gap-2">
          {files.map((f, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-[13px]">
              {f.name.slice(0, 18)}
              <button type="button" aria-label={`Bỏ ảnh ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                <X className="size-3.5" aria-hidden />
              </button>
            </span>
          ))}
          {files.length < MAX_PHOTOS ? (
            <label className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md border border-dashed border-line-strong px-3 text-[14px] hover:border-ink-3">
              <Camera className="size-4" aria-hidden /> Thêm ảnh
              <input type="file" accept="image/*" multiple className="sr-only" onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])].slice(0, MAX_PHOTOS))} />
            </label>
          ) : null}
        </div>
      </div>
      <Input label="Nhận tiền hoàn vào đâu?" hint="Số tài khoản + ngân hàng + tên chủ tài khoản. Không bắt buộc, mình có thể hỏi lại qua Zalo." value={account} onChange={(e) => setAccount(e.target.value)} maxLength={300} />
      {send.error ? (
        <p role="alert" className="text-[14px] text-seal">
          {send.error.message}
        </p>
      ) : null}
      <Button type="submit" size="lg" block loading={send.isPending} disabled={!rating || !liked.trim() || !disliked.trim() || !wouldBuy}>
        Gửi cảm nhận
      </Button>
    </form>
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
