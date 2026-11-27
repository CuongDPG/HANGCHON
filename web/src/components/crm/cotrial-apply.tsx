"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CircleCheck, Users } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/choice";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/field";
import { ImageBox } from "@/components/ui/image-box";
import { Money } from "@/components/ui/money";
import { PageHeader } from "@/components/ui/page-header";
import { publicCotrialApi } from "@/lib/api/crm";
import { CotrialTerms, loadTester, saveTester, type SavedTester } from "./tester-signup";

const TITLE = "Dùng thử cùng mình";

/** Link riêng một lời mời (/dung-thu/m/[token]): xem món, đăng ký thử. Người đã có trong sổ (lưu trên máy này) đăng ký
 *  nhanh; người mới vào sổ người dùng thử cùng lúc. Không có gì về quá trình chọn. Gọi khách là «bạn». */
export function CotrialApply({ token }: { token: string }) {
  const offer = useQuery({ queryKey: ["store", "cotrial-offer", token], queryFn: () => publicCotrialApi.offer(token), retry: false });
  const apply = useMutation({
    mutationFn: (b: Parameters<typeof publicCotrialApi.apply>[1]) => publicCotrialApi.apply(token, b),
    meta: { silentError: true },
  });
  const [saved, setSaved] = useState<SavedTester | null>(null);
  const [edit, setEdit] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [agree, setAgree] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage chỉ đọc được trên máy khách sau khi dựng trang
    setSaved(loadTester());
  }, []);

  if (offer.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title={TITLE} />
        <SkeletonList rows={2} />
      </div>
    );
  }
  if (offer.error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title={TITLE} />
        <EmptyState icon={<Users />} title="Lời mời này không còn mở" description="Có thể đã đủ người hoặc mình đã đóng. Bạn nhắn mình qua Zalo nhé." />
      </div>
    );
  }
  const o = offer.data;
  const fast = saved && !edit;

  async function submit(e: FormEvent) {
    e.preventDefault();
    const who = fast && saved ? saved : { name: name.trim(), phone: phone.trim() || undefined, email: email.trim() || undefined };
    const body = { ...who, interests: [], agree, note: note.trim() || undefined };
    try {
      await apply.mutateAsync(body);
      saveTester({ name: body.name, phone: body.phone, email: body.email });
    } catch {
      /* lỗi hiện ngay dưới form */
    }
  }

  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader eyebrow="Lời mời riêng" title={TITLE} />
      <Card className="flex flex-col gap-3">
        {o.photos.length ? (
          <div className="grid grid-cols-2 gap-2">
            {o.photos.map((p, i) => (
              <ImageBox key={i} src={p.src ?? p.thumb} alt={`${o.title} — ảnh ${i + 1}`} priority={i === 0} />
            ))}
          </div>
        ) : null}
        <h2 className="text-[18px] leading-snug font-semibold">{o.title}</h2>
        {o.description ? <p className="text-[15px] text-ink-2 [text-wrap:pretty]">{o.description}</p> : null}
        <p className="text-[15px]">
          Giá <Money value={o.price_vnd} className="font-semibold" /> · gửi cảm nhận đủ được hoàn <Money value={o.refund_vnd} className="font-semibold" />
        </p>
      </Card>
      <Card tone="soft" className="flex flex-col gap-2">
        <h2 className="text-[16px] font-semibold">Điều kiện</h2>
        <CotrialTerms price={o.price_vnd} refund={o.refund_vnd} days={o.feedback_days} />
        <p className="text-[13.5px] text-ink-2">Mình chọn {o.slots} người trong số bạn đăng ký và nhắn riêng cho người được chọn.</p>
      </Card>
      {apply.isSuccess ? (
        <EmptyState icon={<CircleCheck />} title="Đã nhận đăng ký" description={apply.data.message} />
      ) : o.full ? (
        <EmptyState title="Món này đã đủ người thử" description="Lần sau có món mới mình mời bạn nhé." />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          {fast ? (
            <Card className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[15px]">
                Đăng ký với tên <span className="font-semibold">{saved.name}</span> ({saved.phone ?? saved.email})
              </p>
              <Button type="button" size="sm" variant="ghost" onClick={() => setEdit(true)}>
                Không phải bạn?
              </Button>
            </Card>
          ) : (
            <>
              <Input label="Tên gọi" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="given-name" />
              <Input label="Số điện thoại (Zalo)" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" hint="Hoặc để email bên dưới." />
              <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
              <p className="text-[13px] text-ink-2">Lần đầu đăng ký, bạn được ghi vào sổ người dùng thử để lần sau đăng ký nhanh hơn.</p>
            </>
          )}
          <Textarea label="Vì sao bạn muốn thử món này?" hint="Không bắt buộc." rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
          <Checkbox label="Đã đọc và đồng ý điều kiện ở trên" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          {apply.error ? (
            <p role="alert" className="text-[14px] text-seal">
              {apply.error.message}
            </p>
          ) : null}
          <Button type="submit" size="lg" block loading={apply.isPending} disabled={!agree || (!fast && (!name.trim() || !(phone.trim() || email.trim())))}>
            Đăng ký dùng thử
          </Button>
        </form>
      )}
    </div>
  );
}
