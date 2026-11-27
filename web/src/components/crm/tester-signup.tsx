"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CircleCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip, ChipRow } from "@/components/ui/chip";
import { Checkbox } from "@/components/ui/choice";
import { EmptyState } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { Money } from "@/components/ui/money";
import { publicCotrialApi, type SignupInput } from "@/lib/api/crm";

/** Liên hệ người dùng thử lưu trên máy của chính khách (không hỏi máy chủ) để điền sẵn ở link mời thử. */
const STORE_KEY = "hc.tester";

export type SavedTester = { name: string; phone?: string; email?: string };

export function loadTester(): SavedTester | null {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as SavedTester) : null;
  } catch {
    return null;
  }
}

export function saveTester(t: SavedTester) {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(t));
  } catch {
    /* trình duyệt chặn lưu: bỏ qua */
  }
}

/** Điều kiện dùng thử cùng — có số khi xem một lời mời cụ thể. */
export function CotrialTerms({ price, refund, days }: { price?: number; refund?: number; days?: number }) {
  return (
    <ul className="flex list-disc flex-col gap-1 pl-5 text-[14.5px] [text-wrap:pretty]">
      <li>
        Bạn mua món ở giá thường{price ? (
          <>
            {" "}
            (<Money value={price} />)
          </>
        ) : null}
        , mình gửi hàng như đơn bình thường.
      </li>
      <li>
        Nhận hàng xong, trong {days ? `${days} ngày` : "thời hạn ghi ở lời mời"} bạn gửi cảm nhận theo mẫu: chấm sao, điều thích, điều chưa
        ưng, có mua ở giá này không.
      </li>
      <li>
        Gửi đủ và đúng hạn thì mình hoàn lại{refund ? (
          <>
            {" "}
            <Money value={refund} />
          </>
        ) : " phần tiền ghi ở lời mời"}
        . Quá hạn thì không hoàn, và lần sau mình ưu tiên người khác.
      </li>
      <li>Cảm nhận chỉ để mình quyết định có bán món này hay không, không đăng lên website.</li>
    </ul>
  );
}

/** Sổ người dùng thử (/dung-thu): khách đăng ký một lần; có món đang thử hợp thì mình nhắn link mời riêng. */
export function TesterSignup() {
  const form = useQuery({ queryKey: ["store", "tester-form"], queryFn: () => publicCotrialApi.form() });
  const signup = useMutation({ mutationFn: (b: SignupInput) => publicCotrialApi.signup(b), meta: { silentError: true } });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [agree, setAgree] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { name: name.trim(), phone: phone.trim() || undefined, email: email.trim() || undefined, interests, agree };
    try {
      await signup.mutateAsync(body);
      saveTester({ name: body.name, phone: body.phone, email: body.email });
    } catch {
      /* lỗi hiện ngay dưới form */
    }
  }

  if (signup.isSuccess) {
    return <EmptyState icon={<CircleCheck />} title="Mình đã ghi tên bạn" description={signup.data.message} />;
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Card tone="soft" className="flex flex-col gap-2">
        <h2 className="text-[16px] font-semibold">Điều kiện dùng thử cùng mình</h2>
        <CotrialTerms />
      </Card>
      <Input label="Tên gọi" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required autoComplete="given-name" />
      <Input label="Số điện thoại (Zalo)" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" hint="Hoặc để email bên dưới." />
      <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
      {form.data?.categories.length ? (
        <fieldset className="flex min-w-0 flex-col gap-2">
          <legend className="mb-1 text-[15px] font-semibold">Bạn quan tâm nhóm đồ nào?</legend>
          <ChipRow className="flex-wrap">
            {form.data.categories.map((c) => {
              const on = interests.includes(c.slug);
              return (
                <Chip key={c.slug} selected={on} onClick={() => setInterests(on ? interests.filter((x) => x !== c.slug) : [...interests, c.slug])}>
                  {c.name}
                </Chip>
              );
            })}
          </ChipRow>
        </fieldset>
      ) : null}
      <Checkbox label="Đã đọc và đồng ý điều kiện dùng thử ở trên" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
      {signup.error ? (
        <p role="alert" className="text-[14px] text-seal">
          {signup.error.message}
        </p>
      ) : null}
      <Button type="submit" size="lg" block loading={signup.isPending} disabled={!agree || !name.trim() || !(phone.trim() || email.trim())}>
        Ghi tên vào sổ người dùng thử
      </Button>
    </form>
  );
}
