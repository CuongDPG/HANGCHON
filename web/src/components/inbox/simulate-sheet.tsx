"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Input, InlineSelect, Sheet, Textarea, notifySuccess } from "@/components/ui";
import { useSimulate, type SimulateInput } from "@/lib/api/inbox";

const SAMPLES = [
  "Bình giữ nhiệt giá bao nhiêu shop?",
  "Hộp cơm inox bao giờ về vậy chị?",
  "Đơn của mình nhận bị móp nắp rồi",
  "Mình đang mang thai dùng được không ạ?",
];

/** Giả lập khách bình luận / nhắn tin (chỉ có ở môi trường dev, test) để chạy thử trọn luồng không cần tài khoản. */
export function SimulateSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const simulate = useSimulate();
  const [form, setForm] = useState<SimulateInput>({ text: SAMPLES[0], channel: "facebook", kind: "direct_message", author_name: "Khách thử nghiệm" });

  async function submit() {
    const t = await simulate.mutateAsync(form);
    notifySuccess("Đã giả lập tin đến");
    onClose();
    router.push(`/desk/khach/hoi-thoai/${t.id}`);
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Giả lập tin khách gửi"
      description="Chỉ có trên máy chạy thử. Tin đi qua đúng luồng thật: AI phân loại, soạn nháp hoặc chuyển chị."
      footer={
        <Button block loading={simulate.isPending} disabled={!form.text.trim()} onClick={submit}>
          Gửi tin giả lập
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <InlineSelect
            label="Kênh"
            value={form.channel}
            onChange={(channel) => setForm((f) => ({ ...f, channel, kind: channel === "zalo_oa" ? "direct_message" : f.kind }))}
            options={[
              { value: "facebook", label: "Facebook" },
              { value: "instagram", label: "Instagram" },
              { value: "zalo_oa", label: "Zalo" },
            ]}
          />
          <InlineSelect
            label="Loại"
            value={form.kind}
            onChange={(kind) => setForm((f) => ({ ...f, kind }))}
            options={[
              { value: "direct_message", label: "Tin nhắn" },
              { value: "comment", label: "Bình luận", disabled: form.channel === "zalo_oa" },
            ]}
          />
        </div>
        <Input label="Tên khách" value={form.author_name} onChange={(e) => setForm((f) => ({ ...f, author_name: e.target.value }))} />
        <Textarea label="Nội dung" value={form.text} onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))} rows={3} />
        <div className="flex flex-wrap gap-2">
          {SAMPLES.map((s) => (
            <button
              key={s}
              type="button"
              className="rounded-md border border-line px-2.5 py-1 text-left text-[13px] text-ink-2 hover:border-ink-3 hover:text-ink"
              onClick={() => setForm((f) => ({ ...f, text: s }))}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </Sheet>
  );
}
