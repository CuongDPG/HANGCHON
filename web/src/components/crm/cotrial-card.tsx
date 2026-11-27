"use client";

import { ArrowRight, Copy, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Input, Money, SectionLabel, Segmented, Sheet, Textarea, notifyError, notifySuccess } from "@/components/ui";
import { useCreateOffer, useCotrialOffers, type CotrialOffer, type ImagePick } from "@/lib/api/crm";
import type { TrialNote } from "@/lib/api/selection";
import { useCandidateGallery } from "@/lib/api/sourcing";
import { cn } from "@/lib/cn";

export async function copyLink(link: string) {
  try {
    await navigator.clipboard.writeText(link);
    notifySuccess("Đã chép link");
  } catch {
    notifyError("Trình duyệt không cho chép link.");
  }
}

/** «Mời thử cùng» ở Bàn chọn (món đang mua mẫu / đang thử): lời mời của món + nút tạo lời mời mới. */
export function CotrialCard({ candidateId, title, notes }: { candidateId: string; title: string; notes: TrialNote[] }) {
  const { data } = useCotrialOffers(candidateId);
  const [open, setOpen] = useState(false);
  return (
    <section className="flex flex-col gap-3" aria-label="Mời thử cùng">
      <SectionLabel
        aside={
          <Button size="sm" variant="secondary" icon={<Users className="size-4" aria-hidden />} onClick={() => setOpen(true)}>
            Mời thử cùng
          </Button>
        }
      >
        Mời thử cùng · {data?.length ?? 0}
      </SectionLabel>
      {data?.length ? (
        <ul className="flex flex-col gap-2">
          {data.map((o) => (
            <li key={o.id}>
              <OfferRow o={o} />
            </li>
          ))}
        </ul>
      ) : null}
      <OfferSheet open={open} onClose={() => setOpen(false)} candidateId={candidateId} title={title} notes={notes} />
    </section>
  );
}

function OfferRow({ o }: { o: CotrialOffer }) {
  const applied = Object.values(o.counts).reduce((a, b) => a + (b ?? 0), 0);
  return (
    <Card className="flex items-center gap-3">
      <Link href={`/desk/khach/dung-thu/${o.id}`} className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-[15px] font-semibold">{o.title}</span>
          <Badge tone={o.status === "open" ? "success" : "neutral"}>{o.status === "open" ? "Đang mở" : "Đã đóng"}</Badge>
        </span>
        <span className="block text-[13px] text-ink-2">
          <Money value={o.price_vnd} /> · hoàn <Money value={o.refund_amount_vnd} /> · {applied} người đăng ký · đã chọn {o.taken}/{o.slots}
        </span>
      </Link>
      <Button size="sm" variant="ghost" icon={<Copy className="size-4" aria-hidden />} onClick={() => copyLink(o.link)}>
        Chép link
      </Button>
      <ArrowRight className="size-4 shrink-0 text-ink-3" aria-hidden />
    </Card>
  );
}

type Photo = { key: string; src: string; pick: ImagePick };

function OfferSheet({ open, onClose, candidateId, title, notes }: { open: boolean; onClose: () => void; candidateId: string; title: string; notes: TrialNote[] }) {
  const create = useCreateOffer();
  const gallery = useCandidateGallery(candidateId);
  const [name, setName] = useState(title);
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [refundMode, setRefundMode] = useState<"pct" | "vnd">("pct");
  const [refund, setRefund] = useState("50");
  const [askPrice, setAskPrice] = useState("");
  const [slots, setSlots] = useState("3");
  const [days, setDays] = useState("10");
  const [picked, setPicked] = useState<string[]>([]);

  // ảnh chọn được: ảnh nhà cung cấp đã lưu bản sao + ảnh chị chụp trong ghi chú thử
  const photos: Photo[] = [
    ...(gallery.data?.images ?? []).filter((g) => g.cached).map((g) => ({ key: `s:${g.source_url}`, src: g.src, pick: { kind: "supplier" as const, ref: g.source_url } })),
    ...notes
      .filter((n) => n.author === "owner")
      .flatMap((n) => n.photo_urls.map((u, i) => ({ key: `n:${n.id}:${i}`, src: u, pick: { kind: "note" as const, ref: n.id, index: i } }))),
  ];
  const num = (v: string) => Number(v.replace(/\D/g, "")) || 0;

  async function submit() {
    const res = await create.mutateAsync({
      candidate_id: candidateId,
      title: name.trim() || undefined,
      description: description.trim() || undefined,
      price_vnd: num(price),
      refund_pct: refundMode === "pct" ? num(refund) : null,
      refund_vnd: refundMode === "vnd" ? num(refund) : null,
      ask_price_vnd: askPrice ? num(askPrice) : null,
      slots: num(slots) || 1,
      feedback_days: num(days) || 10,
      images: photos.filter((p) => picked.includes(p.key)).map((p) => p.pick),
    });
    onClose();
    await copyLink(res.link);
    notifySuccess("Đã tạo lời mời. Link riêng đã chép, chị gửi qua Zalo cho người muốn thử nhé.");
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Mời thử cùng"
      footer={
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button loading={create.isPending} disabled={!num(price) || !num(refund)} onClick={submit}>
            Tạo lời mời
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Tên món trên lời mời" value={name} onChange={(e) => setName(e.target.value)} />
        <Textarea label="Mô tả ngắn" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        <Input label="Giá người thử trả" inputMode="numeric" trailing="đ" value={price} onChange={(e) => setPrice(e.target.value)} />
        <div className="flex flex-col gap-1.5">
          <Segmented
            aria-label="Cách tính tiền hoàn"
            value={refundMode}
            onChange={setRefundMode}
            options={[
              { value: "pct", label: "Hoàn theo %" },
              { value: "vnd", label: "Hoàn số tiền" },
            ]}
          />
          <Input label={refundMode === "pct" ? "Hoàn bao nhiêu % giá" : "Số tiền hoàn"} inputMode="numeric" trailing={refundMode === "pct" ? "%" : "đ"} value={refund} onChange={(e) => setRefund(e.target.value)} />
        </div>
        <Input label="Hỏi người thử: giá này có mua không?" placeholder="= giá người thử trả" inputMode="numeric" trailing="đ" value={askPrice} onChange={(e) => setAskPrice(e.target.value)} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Số người thử" inputMode="numeric" value={slots} onChange={(e) => setSlots(e.target.value)} />
          <Input label="Hạn cảm nhận (ngày, từ lúc gửi hàng)" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value)} />
        </div>
        {photos.length ? (
          <fieldset className="flex min-w-0 flex-col gap-2">
            <legend className="mb-1 text-[14px] font-medium">Ảnh trên lời mời (tối đa 4)</legend>
            <div className="grid grid-cols-4 gap-2">
              {photos.map((p) => {
                const on = picked.includes(p.key);
                return (
                  <button
                    key={p.key}
                    type="button"
                    aria-pressed={on}
                    aria-label={on ? "Bỏ chọn ảnh" : "Chọn ảnh"}
                    onClick={() => setPicked((x) => (on ? x.filter((k) => k !== p.key) : x.length < 4 ? [...x, p.key] : x))}
                    className={cn("overflow-hidden rounded-md border-2", on ? "border-accent" : "border-transparent")}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={p.src} alt="" className="aspect-square w-full object-cover" referrerPolicy="no-referrer" />
                  </button>
                );
              })}
            </div>
          </fieldset>
        ) : null}
      </div>
    </Sheet>
  );
}
