"use client";

import { Mic, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Textarea } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Sheet } from "@/components/ui/overlay";
import { cn } from "@/lib/cn";

const EXAMPLES = [
  "Tìm giá phơi đồ gấp gọn dưới 300k, ưu tiên hàng Nhật",
  "Soạn bài Facebook cho Đợt 12",
  "Tuần này món nào bán chạy nhất?",
];

/**
 * Nút nổi «Nói với AI» + bảng nhập lệnh (chức năng i6). Hiện mới là khung giao diện:
 * khi có API ra lệnh, nối ở `submit()` (gọi qua src/lib/api/<module>.ts) và bật nút Gửi, nút ghi âm.
 */
export function CommandButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const connected = false; // TODO(i6): bật khi có endpoint nhận lệnh

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "fixed right-4 bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+14px)] z-20 inline-flex h-12 items-center gap-2 rounded-md bg-ink pr-4 pl-3.5 text-[15px] font-semibold text-paper shadow-pop transition-transform active:scale-[0.97] md:right-8 md:bottom-8",
          className,
        )}
      >
        <Sparkles className="size-[18px]" aria-hidden />
        Nói với AI
      </button>

      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Nói với AI"
        description="Giao việc bằng một câu, như dặn người giúp việc."
        footer={
          <>
            <IconButton label="Ghi âm (sắp có)" icon={<Mic />} variant="secondary" disabled={!connected} className="max-md:flex-none" />
            <Button icon={<Send className="size-4" />} disabled={!connected || !text.trim()}>
              Gửi cho AI
            </Button>
          </>
        }
      >
        <Textarea
          aria-label="Lệnh cho AI"
          placeholder="Chị muốn AI làm gì?"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          hint={connected ? undefined : "Phần ra lệnh sẽ nối với AI ở bước sau. Hiện chưa gửi được."}
        />
        <p className="mt-4 mb-2 text-[13px] font-medium text-ink-2">Ví dụ</p>
        <div className="flex flex-col items-start gap-2">
          {EXAMPLES.map((ex) => (
            <Chip key={ex} onClick={() => setText(ex)} className="h-auto min-h-9 py-1.5 text-left whitespace-normal">
              {ex}
            </Chip>
          ))}
        </div>
      </Sheet>
    </>
  );
}
