"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

/** Web Speech API (Chrome/Safari/Edge) — kiểu tối thiểu vì lib DOM của TypeScript chưa khai báo đủ. */
type RecognitionResult = { isFinal: boolean; 0: { transcript: string } };
type RecognitionEvent = { resultIndex: number; results: ArrayLike<RecognitionResult> };
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type RecognitionCtor = new () => Recognition;

function getCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noop = () => () => {};

/** Nhận giọng nói tiếng Việt (vi-VN). `onText(chữ đã nghe được, đã chốt?)` được gọi liên tục khi đang nghe. */
export function useSpeech(onText: (text: string, final: boolean) => void) {
  const supported = useSyncExternalStore(noop, () => getCtor() !== null, () => false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const cbRef = useRef(onText);
  useEffect(() => {
    cbRef.current = onText;
  });

  const stop = useCallback(() => recRef.current?.stop(), []);

  const start = useCallback(() => {
    const Ctor = getCtor();
    if (!Ctor) {
      setError("Trình duyệt này chưa nghe được giọng nói. Chị gõ giúp em nhé.");
      return;
    }
    setError(null);
    const rec = new Ctor();
    rec.lang = "vi-VN";
    rec.continuous = true;
    rec.interimResults = true;
    let finalText = "";
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      cbRef.current((finalText + interim).trim(), interim === "");
    };
    rec.onerror = (e) => {
      setError(
        e.error === "not-allowed" || e.error === "service-not-allowed"
          ? "Chị cho phép dùng micro trong cài đặt trình duyệt nhé."
          : e.error === "no-speech"
            ? "Em chưa nghe thấy gì, chị nói lại nhé."
            : "Không nghe được, chị thử lại.",
      );
    };
    rec.onend = () => {
      setListening(false);
      recRef.current = null;
    };
    recRef.current = rec;
    setListening(true);
    rec.start();
  }, []);

  useEffect(() => () => recRef.current?.abort(), []);

  return { supported, listening, error, start, stop };
}
