"use client";

import { ChevronUp, PackageCheck, Send } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/field";
import { notifyError, notifySuccess } from "@/components/ui/toast";
import { catalogApi, type FindRequestPublic } from "@/lib/api/catalog";
import { cn } from "@/lib/cn";

const STATUS_TONE: Record<string, string> = {
  new: "border-line-strong text-ink-2",
  threshold: "border-accent text-accent",
  searching: "border-review text-review",
  trying: "border-ink bg-ink text-paper",
  found: "border-auto bg-auto-wash text-auto",
  none: "border-line text-ink-3",
};

/** Bảng Nhờ tìm (e9): gửi nhu cầu, bấm «mình cũng cần» (mỗi thiết bị một lượt), xem trạng thái công khai. */
export function FindBoard({ initial, threshold, prefill }: { initial: FindRequestPublic[]; threshold: number; prefill?: string }) {
  const [items, setItems] = useState(initial);
  const [title, setTitle] = useState(prefill ?? "");
  const [more, setMore] = useState(false);
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [trap, setTrap] = useState("");
  const [sending, setSending] = useState(false);
  const [voting, setVoting] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  function upsert(req: FindRequestPublic) {
    setItems((list) => {
      const rest = list.filter((x) => x.slug !== req.slug);
      return [req, ...rest].sort((a, b) => b.vote_count - a.vote_count);
    });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      const res = await catalogApi.createFind({
        title: title.trim(),
        description: description.trim() || undefined,
        contact: contact.trim() || undefined,
        website: trap || undefined,
      });
      if (res.duplicate) {
        upsert(res.request);
        notifySuccess("Đã có người nhờ tìm món này, mình tính thêm bạn vào số người cùng cần.");
      } else {
        setSent(res.request.title);
      }
      setTitle("");
      setDescription("");
      setContact("");
      setMore(false);
    } catch (err) {
      notifyError(err);
    } finally {
      setSending(false);
    }
  }

  async function vote(slug: string) {
    setVoting(slug);
    try {
      const res = await catalogApi.vote(slug);
      upsert(res.request);
    } catch (err) {
      notifyError(err);
    } finally {
      setVoting(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={submit} className="flex flex-col gap-3" aria-label="Gửi lời nhờ tìm">
        <div className="flex gap-2">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Viết vài chữ… vd. bình sữa thuỷ tinh cho bé"
            aria-label="Món bạn cần tìm"
            wrapperClassName="flex-1"
            maxLength={200}
            required
            minLength={6}
          />
          <Button type="submit" loading={sending} disabled={title.trim().length < 6} icon={<Send className="size-4" />}>
            Gửi
          </Button>
        </div>
        {/* ô bẫy chống máy gửi: người thật không thấy */}
        <input
          type="text"
          name="website"
          value={trap}
          onChange={(e) => setTrap(e.target.value)}
          tabIndex={-1}
          autoComplete="off"
          aria-hidden
          className="absolute -left-[9999px] h-0 w-0 opacity-0"
        />
        {more ? (
          <div className="flex flex-col gap-3">
            <Textarea label="Mô tả thêm (không bắt buộc)" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000} rows={2} />
            <Input
              label="Số điện thoại / Zalo để mình báo khi tìm được (không bắt buộc)"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              inputMode="tel"
              maxLength={200}
            />
          </div>
        ) : (
          <button type="button" onClick={() => setMore(true)} className="self-start text-[14px] text-accent hover:underline">
            + Thêm mô tả, để lại liên hệ
          </button>
        )}
      </form>
      {sent ? (
        <Card tone="soft" role="status">
          <p className="text-[15px]">
            Đã nhận «{sent}». Mình xem qua rồi mới hiện lên bảng để mọi người cùng bấm.
          </p>
        </Card>
      ) : null}

      {items.length ? (
        <ul className="flex flex-col gap-3">
          {items.map((r) => {
            const votable = ["new", "threshold", "searching", "trying"].includes(r.status.key);
            return (
              <li key={r.slug}>
                <Card className="flex flex-col gap-2.5">
                  <p className="text-[16px] font-semibold [text-wrap:pretty]">{r.title}</p>
                  {r.description ? <p className="text-[14px] text-ink-2">{r.description}</p> : null}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => vote(r.slug)}
                      disabled={!votable || r.voted || voting === r.slug}
                      aria-pressed={r.voted}
                      className={cn(
                        "inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-[14px] transition-colors disabled:cursor-default",
                        r.voted ? "border-accent bg-accent-wash text-accent" : "border-line-strong hover:border-ink-3",
                      )}
                    >
                      <ChevronUp className="size-4" aria-hidden />
                      <span className="tabular-nums font-semibold">{r.vote_count}</span>
                      {r.voted ? "người cùng cần · có bạn" : "người cùng cần"}
                    </button>
                    {r.product_slug ? (
                      <Link
                        href={`/san-pham/${r.product_slug}`}
                        className={cn("inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-[13px] font-medium", STATUS_TONE.found)}
                      >
                        <PackageCheck className="size-3.5" aria-hidden /> {r.status.label}
                      </Link>
                    ) : (
                      <span className={cn("rounded-md border px-2.5 py-1 text-[13px] font-medium", STATUS_TONE[r.status.key] ?? STATUS_TONE.new)}>
                        {r.status.label}
                      </span>
                    )}
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState title="Chưa có lời nhờ tìm nào" description="Bạn là người đầu tiên. Gửi món bạn cần ở ô phía trên nhé." />
      )}
      <p className="text-[14px] text-ink-2">Món nào đủ {threshold} người cùng cần, mình sẽ mở tìm. Không tìm được món ưng thì mình nói thẳng.</p>
    </div>
  );
}
