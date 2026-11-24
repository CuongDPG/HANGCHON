"use client";

import { Camera, Link2, Mic, Sparkles, Square } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button, Card, Chip, Textarea, notifyError } from "@/components/ui";
import { useCreateBrief } from "@/lib/api/sourcing";
import { ImageSheet } from "./image-sheet";
import { LinkSheet } from "./link-sheet";
import { useSpeech } from "./use-speech";

const EXAMPLE =
  "Tìm giá phơi đồ gấp gọn cho ban công nhỏ, inox không gỉ, dưới 300k, ưu tiên hàng Nhật hoặc xưởng Trung Quốc có đánh giá tốt";

/** a1 — Ra đề bằng lời: gõ hoặc nói (vi-VN). AI đọc đề → sang trang đề để chị xem «AI hiểu là». */
export function BriefComposer() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [sheet, setSheet] = useState<"link" | "image" | null>(null);
  const base = useRef("");
  const create = useCreateBrief();
  const speech = useSpeech((heard) => {
    setText((base.current ? base.current + " " : "") + heard);
    setMode("voice");
  });

  function toggleMic() {
    if (speech.listening) return speech.stop();
    base.current = text.trim();
    speech.start();
  }

  function submit() {
    if (speech.listening) speech.stop();
    create.mutate(
      { text: text.trim(), input_mode: mode },
      { onSuccess: (b) => router.push(`/desk/san-hang/de/${b.id}`), onError: notifyError },
    );
  }

  return (
    <Card className="flex flex-col gap-3">
      <Textarea
        aria-label="Chị muốn tìm gì?"
        placeholder={`Dặn như dặn người giúp việc, vd. «${EXAMPLE}»`}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (!speech.listening) setMode("text");
        }}
        rows={4}
        error={speech.error ?? undefined}
        hint={speech.listening ? "Em đang nghe… nói xong chị bấm Dừng." : undefined}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Chip
          selected={speech.listening}
          onClick={toggleMic}
          icon={speech.listening ? <Square aria-hidden /> : <Mic aria-hidden />}
          aria-label={speech.listening ? "Dừng nghe" : "Nói tiêu chí"}
          disabled={!speech.supported && !speech.error}
          title={speech.supported ? undefined : "Trình duyệt này chưa hỗ trợ nhận giọng nói"}
        >
          {speech.listening ? "Dừng" : "Nói"}
        </Chip>
        <Chip icon={<Camera aria-hidden />} onClick={() => setSheet("image")}>
          Chụp ảnh
        </Chip>
        <Chip icon={<Link2 aria-hidden />} onClick={() => setSheet("link")}>
          Dán link
        </Chip>
        <Button
          className="ml-auto max-sm:w-full"
          icon={<Sparkles className="size-4" />}
          disabled={text.trim().length < 3}
          loading={create.isPending}
          onClick={submit}
        >
          AI đọc đề
        </Button>
      </div>
      {!text ? (
        <button type="button" className="self-start text-left text-[13px] text-ink-3 underline underline-offset-2" onClick={() => setText(EXAMPLE)}>
          Dùng đề mẫu
        </button>
      ) : null}
      <LinkSheet open={sheet === "link"} onClose={() => setSheet(null)} />
      <ImageSheet open={sheet === "image"} onClose={() => setSheet(null)} />
    </Card>
  );
}
