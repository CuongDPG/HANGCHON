"use client";

import { Check, CircleAlert, Mic, MicOff } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Badge, type BadgeTone } from "@/components/ui";
import type { CheckFinding, ContentChannel, DisplayStatus, Draft } from "@/lib/api/content";
import { cn } from "@/lib/cn";

export const CHANNEL_LABEL: Record<ContentChannel, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  threads: "Threads",
  tiktok: "TikTok",
  zalo_oa: "Zalo",
};

const CHANNEL_MARK: Record<ContentChannel, string> = { facebook: "f", instagram: "IG", threads: "@", tiktok: "TT", zalo_oa: "Z" };

/** Dấu nhận diện kênh (chữ viết tắt, không dùng logo thương hiệu). */
export function ChannelMark({ channel, className }: { channel: ContentChannel; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-grid size-6 shrink-0 place-items-center rounded-sm bg-soft font-display text-[11px] font-bold text-accent",
        className,
      )}
    >
      {CHANNEL_MARK[channel] ?? "·"}
    </span>
  );
}

export const DISPLAY_STATUS: Record<DisplayStatus, { label: string; tone: BadgeTone }> = {
  published: { label: "Đã đăng", tone: "success" },
  draft_pushed: { label: "Nháp TikTok, chờ chị bấm đăng", tone: "warning" },
  approved: { label: "Đã duyệt, chờ giờ", tone: "accent" },
  pending: { label: "Chờ chị duyệt", tone: "neutral" },
  needs_fix: { label: "Cần sửa", tone: "danger" },
  failed: { label: "Đăng lỗi", tone: "danger" },
  publishing: { label: "Đang đăng", tone: "accent" },
  hidden: { label: "Đã ẩn (ngừng bán)", tone: "neutral" },
  removed: { label: "Đã gỡ (ngừng bán)", tone: "neutral" },
};

export function StatusBadge({ status }: { status: DisplayStatus }) {
  const s = DISPLAY_STATUS[status] ?? DISPLAY_STATUS.pending;
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

/** Trạng thái một bản nháp ở xưởng (theo bản nháp + bài trên lịch). */
export function draftDisplay(d: Draft): DisplayStatus | "drafting" {
  if (d.status === "drafting") return "drafting";
  if (d.post?.status === "published" || d.status === "published") return "published";
  if (d.post?.status === "draft_pushed") return "draft_pushed";
  if (d.post?.status === "failed") return "failed";
  if (d.post?.status === "approved" || d.status === "scheduled") return "approved";
  if (!d.can_approve) return "needs_fix";
  return "pending";
}

export function isDone(d: Draft) {
  const s = draftDisplay(d);
  return s === "approved" || s === "published" || s === "draft_pushed";
}

/** Chip ✓/! của soát lời (f5). */
export function CheckChips({ findings, onOverride }: { findings: CheckFinding[]; onOverride?: (f: CheckFinding) => void }) {
  if (!findings.length) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Kết quả soát lời">
      {findings.map((f) => {
        const ok = f.ok || f.overridden;
        return (
          <li key={f.key}>
            <button
              type="button"
              disabled={f.ok || !onOverride}
              onClick={() => onOverride?.(f)}
              title={f.detail}
              className={cn(
                "inline-flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 py-1 text-left text-[13px]",
                f.ok
                  ? "border-transparent bg-auto-wash text-auto"
                  : f.overridden
                    ? "border-transparent bg-review-wash text-review"
                    : "border-seal/40 bg-seal-wash text-seal hover:border-seal",
                ok && "cursor-default",
              )}
            >
              {ok ? <Check className="size-3.5 shrink-0" aria-hidden /> : <CircleAlert className="size-3.5 shrink-0" aria-hidden />}
              <span>
                {f.label}
                {f.overridden ? " · đã bỏ qua" : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

const SECTIONS = [
  { href: "/desk/noi-dung", label: "Xưởng" },
  { href: "/desk/noi-dung/lich", label: "Lịch đăng" },
  { href: "/desk/noi-dung/so-lieu", label: "Bài ra đơn" },
  { href: "/desk/noi-dung/giong", label: "Giọng của chị" },
  { href: "/desk/noi-dung/video", label: "Video ngắn" },
  { href: "/desk/noi-dung/livestream", label: "Livestream" },
];

/** Điều hướng các mục con của khu Nội dung. */
export function ContentNav() {
  const path = usePathname();
  return (
    <nav aria-label="Mục nội dung" className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0">
      {SECTIONS.map((s) => {
        const on = s.href === "/desk/noi-dung" ? path === s.href : path.startsWith(s.href);
        return (
          <Link
            key={s.href}
            href={s.href}
            aria-current={on ? "page" : undefined}
            className={cn(
              "inline-flex h-9 shrink-0 items-center rounded-md border px-3 text-sm whitespace-nowrap transition-colors",
              on ? "border-ink bg-ink text-paper" : "border-line-strong bg-surface text-ink hover:border-ink-3",
            )}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** URL tệp từ API (tuyệt đối) → đường dẫn cùng origin để cookie đăng nhập đi kèm. */
export function localFile(url: string | null | undefined): string | null {
  if (!url) return null;
  const i = url.indexOf("/api/files/");
  return i >= 0 ? url.slice(i) : url;
}

/** Giá trị cho <input type="datetime-local"> theo giờ máy (máy của chị ở giờ Việt Nam). */
export function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ---- Web Speech: nói ý của chị (vi-VN) ----------------------------------------------------------------------

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
};

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noopSubscribe = () => () => {};

/** Ghi lời nói tiếng Việt thành chữ bằng Web Speech API của trình duyệt. Không hỗ trợ → `supported=false`. */
export function useSpeech(onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const supported = useSyncExternalStore(noopSubscribe, () => !!recognitionCtor(), () => false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const cb = useRef(onText);
  useEffect(() => {
    cb.current = onText;
  });
  useEffect(() => () => rec.current?.stop(), []);

  const start = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = "vi-VN";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      const text = Array.from(e.results)
        .map((x) => x[0]?.transcript ?? "")
        .join(" ")
        .trim();
      cb.current(text);
    };
    r.onerror = (e) => setError(e.error === "not-allowed" ? "Chị cho phép dùng micro để nói nhé." : "Chưa nghe rõ, chị thử lại.");
    r.onend = () => setListening(false);
    setError(null);
    rec.current = r;
    r.start();
    setListening(true);
  }, []);

  const stop = useCallback(() => rec.current?.stop(), []);
  return { supported, listening, error, start, stop };
}

export function MicButton({ listening, onClick, disabled }: { listening: boolean; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={listening}
      className={cn(
        "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-3 text-sm whitespace-nowrap",
        listening ? "border-seal bg-seal-wash text-seal" : "border-line-strong bg-surface text-ink hover:border-ink-3",
        "disabled:opacity-50",
      )}
    >
      {listening ? <MicOff className="size-4" aria-hidden /> : <Mic className="size-4" aria-hidden />}
      {listening ? "Đang nghe… bấm để dừng" : "Nói ý của chị"}
    </button>
  );
}
