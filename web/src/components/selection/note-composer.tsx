"use client";

import { AudioLines, Camera, Mic, Square, X } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Button, IconButton, Textarea, notifySuccess } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useCreateNote, type TrialNote } from "@/lib/api/selection";

/* ---------- Web Speech API (vi-VN) ---------- */

type RecognitionResult = { isFinal: boolean; 0: { transcript: string } };
type RecognitionEvent = { resultIndex: number; results: ArrayLike<RecognitionResult> };
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
};
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noop = () => () => {};

/** Nghe chị nói bằng nhận dạng giọng nói của trình duyệt. `supported = false` thì ẩn micro. */
function useSpeech(onFinal: (text: string) => void) {
  const supported = useSyncExternalStore(noop, () => recognitionCtor() !== null, () => false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const startedAt = useRef<number>(0);
  const onFinalRef = useRef(onFinal);
  useEffect(() => {
    onFinalRef.current = onFinal;
  });
  useEffect(() => () => rec.current?.stop(), []);

  function start() {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = "vi-VN";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let tmp = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) onFinalRef.current(res[0].transcript.trim());
        else tmp += res[0].transcript;
      }
      setInterim(tmp);
    };
    r.onerror = (e) => setError(e.error === "not-allowed" ? "Chị cho phép dùng micro trong trình duyệt nhé." : "Micro tạm không nghe được.");
    r.onend = () => {
      setListening(false);
      setInterim("");
    };
    rec.current = r;
    setError(null);
    startedAt.current = Date.now();
    r.start();
    setListening(true);
  }

  function stop() {
    rec.current?.stop();
  }

  return { supported, listening, interim, error, start, stop, seconds: () => (Date.now() - startedAt.current) / 1000 };
}

/* ---------- ô ghi chú ---------- */

/**
 * Ghi chú thử hàng (c2): gõ hoặc nói (vi-VN), kèm ảnh, có thể tải file ghi âm lên lưu kèm.
 * `candidateId = null` → ghi nhanh, AI tự xếp vào món đang thử.
 */
export function NoteComposer({
  candidateId,
  onSaved,
  compact = false,
}: {
  candidateId: string | null;
  onSaved?: (n: TrialNote) => void;
  compact?: boolean;
}) {
  const [text, setText] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [audio, setAudio] = useState<File | null>(null);
  const [spoken, setSpoken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const audioInput = useRef<HTMLInputElement>(null);
  const create = useCreateNote(candidateId);
  const speech = useSpeech((t) => {
    if (!t) return;
    setText((cur) => (cur.trim() ? `${cur.trim()} ${t}` : t));
    setError(null);
  });
  const previews = usePreviews(photos);

  async function save() {
    if (!text.trim() && !photos.length && !audio) {
      setError("Chị nói, gõ hoặc thêm ảnh trước nhé.");
      return;
    }
    if (speech.listening) speech.stop();
    const n = await create.mutateAsync({ text: text.trim(), voice: spoken > 0, photos, audio, durationSeconds: spoken || undefined });
    setText("");
    setPhotos([]);
    setAudio(null);
    setSpoken(0);
    const pts = n.points.length;
    if (!candidateId) {
      notifySuccess(n.candidate_id ? "Đã lưu và xếp vào món đang thử" : "Đã lưu; AI chưa chắc là món nào, chị chọn giúp");
    } else {
      notifySuccess(pts ? `Đã lưu, AI sắp thành ${pts} ý` : "Đã lưu ghi chú");
    }
    onSaved?.(n);
  }

  return (
    <div className={cn("flex flex-col gap-3", !compact && "rounded-md border border-line bg-surface p-3")}>
      <Textarea
        aria-label="Ghi chú thử hàng"
        placeholder={speech.supported ? "Bấm «Nói» rồi kể vài câu trong lúc dùng, hoặc gõ ở đây…" : "Gõ vài câu nhận xét trong lúc dùng…"}
        value={speech.interim ? `${text}${text ? " " : ""}${speech.interim}` : text}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
        }}
        // đang lưu thì khoá ô: chữ gõ trong lúc chờ sẽ bị xoá khi lưu xong
        readOnly={speech.listening || create.isPending}
        rows={compact ? 3 : 2}
        error={error ?? speech.error}
      />
      {previews.length || audio ? (
        <div className="flex flex-wrap items-center gap-2">
          {previews.map((p, i) => (
            <span key={p.url} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element -- ảnh xem trước cục bộ (blob:) */}
              <img src={p.url} alt={`Ảnh ${i + 1}`} className="size-14 rounded-md object-cover" />
              <button
                type="button"
                aria-label={`Bỏ ảnh ${i + 1}`}
                onClick={() => setPhotos((xs) => xs.filter((_, j) => j !== i))}
                className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full bg-ink text-paper"
              >
                <X className="size-3" aria-hidden />
              </button>
            </span>
          ))}
          {audio ? (
            <span className="inline-flex h-9 items-center gap-1.5 rounded-md bg-soft px-2 text-[13px]">
              <AudioLines className="size-4" aria-hidden />
              <span className="max-w-40 truncate">{audio.name}</span>
              <IconButton size="sm" label="Bỏ ghi âm" icon={<X />} onClick={() => setAudio(null)} className="-mr-1 size-7" />
            </span>
          ) : null}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {speech.supported ? (
          speech.listening ? (
            <Button
              size="sm"
              variant="danger"
              icon={<Square className="size-3.5" aria-hidden />}
              onClick={() => {
                setSpoken((s) => s + speech.seconds());
                speech.stop();
              }}
            >
              Đang nghe… bấm để dừng
            </Button>
          ) : (
            <Button size="sm" variant="secondary" icon={<Mic className="size-4" aria-hidden />} onClick={speech.start}>
              Nói
            </Button>
          )
        ) : null}
        <Button size="sm" variant="secondary" icon={<Camera className="size-4" aria-hidden />} onClick={() => photoInput.current?.click()}>
          Thêm ảnh
        </Button>
        <Button size="sm" variant="ghost" icon={<AudioLines className="size-4" aria-hidden />} onClick={() => audioInput.current?.click()}>
          Tệp ghi âm
        </Button>
        <Button size="sm" className="ml-auto" loading={create.isPending} onClick={save}>
          Lưu ghi chú
        </Button>
      </div>
      <input
        ref={photoInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          setPhotos((xs) => [...xs, ...files].slice(0, 6));
          e.target.value = "";
        }}
      />
      <input
        ref={audioInput}
        type="file"
        accept="audio/*"
        hidden
        onChange={(e) => {
          setAudio(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function usePreviews(files: File[]) {
  const [urls, setUrls] = useState<{ file: File; url: string }[]>([]);
  useEffect(() => {
    const next = files.map((file) => ({ file, url: URL.createObjectURL(file) }));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- đồng bộ URL xem trước với danh sách tệp
    setUrls(next);
    return () => next.forEach((p) => URL.revokeObjectURL(p.url));
  }, [files]);
  return urls;
}
