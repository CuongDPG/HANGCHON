"use client";

import { CircleAlert, CircleCheck, CircleHelp, Mic, Send, Sparkles, Square } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Button, ButtonLink, Chip, IconButton, Sheet, Textarea } from "@/components/ui";
import { useCommand, useIntents, type CommandResult } from "@/lib/api/control";
import { cn } from "@/lib/cn";

const FALLBACK_EXAMPLES = ["Có việc gì chờ chị duyệt không?", "Tìm giá phơi đồ gấp gọn dưới 300k, ưu tiên hàng Nhật", "Soạn bài Facebook cho Đợt 12"];

/* ---------- Web Speech API (vi-VN) ---------- */

type RecognitionResultEvent = { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> };
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: RecognitionResultEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noop = () => () => {};
/** Trình duyệt có nhận giọng nói không (máy chủ luôn trả false để không lệch khi hydrate). */
function useSpeechSupported(): boolean {
  return useSyncExternalStore(noop, () => recognitionCtor() !== null, () => false);
}

const SPEECH_ERRORS: Record<string, string> = {
  "not-allowed": "Trình duyệt chưa cho dùng micro. Chị bật quyền micro rồi thử lại.",
  "service-not-allowed": "Trình duyệt chưa cho dùng micro. Chị bật quyền micro rồi thử lại.",
  "no-speech": "Em chưa nghe thấy gì. Chị nói lại nhé.",
  network: "Nhận giọng nói cần mạng. Kiểm tra mạng rồi thử lại.",
  "audio-capture": "Không thấy micro trên máy.",
};

/**
 * Nút nổi «Nói với AI» + bảng giao việc (i6): gõ hoặc nói (vi-VN), gửi tới `POST /api/desk/control/command`,
 * hiện kết quả và đường dẫn tới việc vừa tạo.
 */
export function CommandButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
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
      <CommandSheet open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function CommandSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const [text, setText] = useState("");
  const [result, setResult] = useState<CommandResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const baseRef = useRef("");
  const speech = useSpeechSupported();
  const intents = useIntents(open);
  const command = useCommand();

  const examples = (intents.data ?? []).flatMap((i) => i.examples.slice(0, 1)).slice(0, 4);

  // Đóng sheet hoặc rời trang thì dừng ghi âm
  useEffect(() => {
    if (!open) recRef.current?.abort();
  }, [open]);
  useEffect(() => () => recRef.current?.abort(), []);

  function startListening() {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    setSpeechError(null);
    const rec = new Ctor();
    rec.lang = "vi-VN";
    rec.interimResults = true;
    rec.continuous = false;
    baseRef.current = text ? `${text.trimEnd()} ` : "";
    rec.onresult = (e) => {
      let said = "";
      for (let i = 0; i < e.results.length; i++) said += e.results[i][0].transcript;
      setText(baseRef.current + said);
    };
    rec.onerror = (e) => {
      if (e.error !== "aborted") setSpeechError(SPEECH_ERRORS[e.error] ?? "Không nhận được giọng nói. Chị gõ giúp em nhé.");
    };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch {
      setSpeechError("Không bật được micro. Chị gõ giúp em nhé.");
    }
  }

  function stopListening() {
    recRef.current?.stop();
  }

  async function submit() {
    const t = text.trim();
    if (!t) return;
    recRef.current?.abort();
    setFailure(null);
    try {
      const res = await command.mutateAsync({ text: t, context: { path: pathname } });
      setResult(res);
      if (res.status === "done") setText("");
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "Chưa gửi được. Thử lại nhé.");
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Nói với AI"
      description="Giao việc bằng một câu, như dặn người giúp việc."
      footer={
        <>
          {speech ? (
            listening ? (
              <IconButton label="Dừng ghi âm" icon={<Square />} variant="primary" onClick={stopListening} className="max-md:flex-none" />
            ) : (
              <IconButton label="Nói bằng giọng" icon={<Mic />} variant="secondary" onClick={startListening} className="max-md:flex-none" />
            )
          ) : null}
          <Button icon={<Send className="size-4" />} loading={command.isPending} disabled={!text.trim()} onClick={submit}>
            Gửi cho AI
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Textarea
          aria-label="Lệnh cho AI"
          placeholder={listening ? "Em đang nghe…" : "Chị muốn AI làm gì?"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
          }}
          rows={3}
          hint={speechError ?? (listening ? "Đang nghe… nói xong em tự dừng." : undefined)}
        />
      </form>

      {failure ? (
        <ResultCard tone="error" icon={<CircleAlert className="size-5 text-seal" aria-hidden />} title="Chưa gửi được" message={failure} />
      ) : result ? (
        <ResultCard
          tone={result.status === "done" ? "ok" : result.status === "failed" ? "error" : "ask"}
          icon={
            result.status === "done" ? (
              <CircleCheck className="size-5 text-auto" aria-hidden />
            ) : result.status === "failed" ? (
              <CircleAlert className="size-5 text-seal" aria-hidden />
            ) : (
              <CircleHelp className="size-5 text-review" aria-hidden />
            )
          }
          title={result.status === "done" ? `Đã giao: ${result.label}` : result.status === "failed" ? "Chưa làm được" : "Em cần chị nói rõ hơn"}
          message={result.message}
          href={result.href}
          onNavigate={onClose}
        />
      ) : null}

      <p className="mt-4 mb-2 text-[13px] font-medium text-ink-2">Ví dụ</p>
      <div className="flex flex-col items-start gap-2">
        {(examples.length ? examples : FALLBACK_EXAMPLES).map((ex) => (
          <Chip key={ex} onClick={() => setText(ex)} className="h-auto min-h-9 py-1.5 text-left whitespace-normal">
            {ex}
          </Chip>
        ))}
      </div>
    </Sheet>
  );
}

function ResultCard({
  tone,
  icon,
  title,
  message,
  href,
  onNavigate,
}: {
  tone: "ok" | "ask" | "error";
  icon: React.ReactNode;
  title: string;
  message: string;
  href?: string | null;
  onNavigate?: () => void;
}) {
  return (
    <div
      role="status"
      className={cn(
        "mt-4 flex gap-3 rounded-md p-3",
        tone === "ok" ? "bg-auto-wash" : tone === "ask" ? "bg-review-wash" : "bg-seal-wash",
      )}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold">{title}</p>
        <p className="text-[14px] text-ink [overflow-wrap:anywhere]">{message}</p>
        {href ? (
          <ButtonLink href={href} size="sm" variant="secondary" className="mt-2" onClick={onNavigate}>
            Mở →
          </ButtonLink>
        ) : null}
      </div>
    </div>
  );
}
