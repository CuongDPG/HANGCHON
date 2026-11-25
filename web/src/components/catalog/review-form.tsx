"use client";

import { Camera, Star, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/field";
import { notifyError } from "@/components/ui/toast";
import { catalogApi, type ReviewInvite } from "@/lib/api/catalog";
import { cn } from "@/lib/cn";

const MAX_PHOTOS = 4;
const LABELS = ["", "Không ưng", "Chưa ổn", "Tạm được", "Ưng", "Rất ưng"];

/** Khách gửi sao + chữ + ảnh (e8). Ảnh được bỏ thông tin vị trí trước khi lưu. */
export function ReviewForm({ token, invite }: { token: string; invite: ReviewInvite }) {
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [name, setName] = useState(invite.display_name ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [state, setState] = useState(invite.status);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!rating) return;
    setSending(true);
    const form = new FormData();
    form.append("rating", String(rating));
    if (body.trim()) form.append("body", body.trim());
    if (name.trim()) form.append("display_name", name.trim());
    files.forEach((f) => form.append("photos", f));
    try {
      const res = await catalogApi.submitReview(token, form);
      setState(res.status);
    } catch (err) {
      notifyError(err);
    } finally {
      setSending(false);
    }
  }

  if (state !== "requested") {
    return (
      <Card tone="soft" role="status">
        <p className="text-[16px] font-semibold">{state === "expired" ? "Đường link đã hết hạn" : "Cảm ơn bạn đã đánh giá!"}</p>
        <p className="mt-1 text-[15px] text-ink-2">
          {state === "expired"
            ? "Bạn nhắn mình qua Zalo nếu vẫn muốn gửi cảm nhận nhé."
            : "Mình đọc từng đánh giá trước khi hiện lên trang. Lời chê thật lòng vẫn được hiện."}
        </p>
      </Card>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-[15px] font-semibold">Bạn chấm mấy sao?</legend>
        <div className="flex items-center gap-1" role="radiogroup" aria-label="Số sao">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={rating === n}
              aria-label={`${n} sao`}
              onClick={() => setRating(n)}
              className="grid size-11 place-items-center rounded-md hover:bg-soft"
            >
              <Star className={cn("size-7", n <= rating ? "fill-review text-review" : "text-line-strong")} aria-hidden />
            </button>
          ))}
          <span className="ml-2 text-[14px] text-ink-2">{LABELS[rating]}</span>
        </div>
      </fieldset>
      <Textarea label="Bạn dùng thấy thế nào?" value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={4}
        hint="Cả điều chưa ưng cũng rất có ích cho người mua sau." />
      <div className="flex flex-col gap-2">
        <span className="text-[15px] font-semibold">Ảnh bạn chụp (tối đa {MAX_PHOTOS})</span>
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
              <input
                type="file"
                accept="image/*"
                multiple
                className="sr-only"
                onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])].slice(0, MAX_PHOTOS))}
              />
            </label>
          ) : null}
        </div>
      </div>
      <Input label="Tên hiện trên đánh giá" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} hint="Chỉ tên gọi, không cần họ." />
      <Button type="submit" size="lg" block loading={sending} disabled={!rating}>
        Gửi đánh giá
      </Button>
    </form>
  );
}
