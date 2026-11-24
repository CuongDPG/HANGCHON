"use client";

import { Bot, CornerDownLeft, Send, ThumbsDown, ThumbsUp, UserRound } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { notifyError, notifySuccess } from "@/components/ui/toast";
import { assistantApi, conversationStorageKey, type AssistantConversation, type AssistantMessage } from "@/lib/api/assistant";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/cn";

type AskBoxProps = {
  /** Có thì hỏi về đúng món này (trả lời từ hồ sơ của món); không có thì hỏi chung về các món trên kệ. */
  productSlug?: string | null;
  productName?: string | null;
  /** Câu hỏi gợi ý bấm nhanh. */
  suggestions?: string[];
  placeholder?: string;
  className?: string;
};

/**
 * Hỏi trợ lý (e7): trả lời chỉ từ hồ sơ của chị, mỗi câu dẫn về một mục trong hồ sơ.
 * Không có dữ liệu → nói không biết, chuyển cho chị; chị trả lời thì hiện ở đây khi khách mở lại.
 */
export function AskBox({ productSlug, productName, suggestions = [], placeholder, className }: AskBoxProps) {
  const [conv, setConv] = useState<AssistantConversation | null>(null);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState("");
  const listRef = useRef<HTMLOListElement>(null);
  const storageKey = conversationStorageKey(productSlug);

  // mở lại cuộc trò chuyện cũ trong phiên (để thấy câu chị trả lời)
  useEffect(() => {
    const id = sessionStorage.getItem(storageKey);
    if (!id) return;
    let alive = true;
    assistantApi
      .conversation(id)
      .then((c) => alive && setConv(c))
      .catch(() => sessionStorage.removeItem(storageKey));
    return () => {
      alive = false;
    };
  }, [storageKey]);

  useEffect(() => {
    listRef.current?.lastElementChild?.scrollIntoView({ block: "nearest" });
  }, [conv?.messages.length]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || sending) return;
    setSending(true);
    setError(null);
    try {
      const res = await assistantApi.ask({
        question: q,
        product_slug: productSlug ?? null,
        conversation_id: conv?.id ?? null,
        page_path: typeof window !== "undefined" ? window.location.pathname : undefined,
      });
      setConv(res.conversation);
      sessionStorage.setItem(storageKey, res.conversation.id);
      setQuestion("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  async function saveContact(e: FormEvent) {
    e.preventDefault();
    if (!conv || contact.trim().length < 6) return;
    try {
      setConv(await assistantApi.contact(conv.id, contact.trim()));
      notifySuccess("Đã lưu, chị sẽ nhắn lại cho bạn.");
    } catch (err) {
      notifyError(err);
    }
  }

  async function rate(m: AssistantMessage, value: "up" | "down") {
    if (!conv) return;
    try {
      setConv(await assistantApi.feedback(conv.id, m.id, value));
    } catch (err) {
      notifyError(err);
    }
  }

  const messages = conv?.messages ?? [];
  const handedOff = messages.some((m) => m.role === "assistant" && m.unknown);
  return (
    <section className={cn("flex flex-col gap-3", className)} aria-label={productName ? `Hỏi về ${productName}` : "Hỏi trợ lý"}>
      {messages.length ? (
        <ol ref={listRef} className="flex flex-col gap-2.5" aria-live="polite">
          {messages.map((m) => (
            <li key={m.id} className={cn("flex flex-col gap-1", m.role === "user" ? "items-end" : "items-start")}>
              <div
                className={cn(
                  "max-w-[88%] rounded-md px-3.5 py-2.5 text-[15px] leading-relaxed",
                  m.role === "user" ? "bg-ink text-paper" : m.role === "owner" ? "border border-accent bg-accent-wash" : "bg-soft",
                )}
              >
                {m.role !== "user" ? (
                  <span className="mb-1 flex items-center gap-1.5 text-[12px] font-semibold text-ink-2">
                    {m.role === "owner" ? <UserRound className="size-3.5" aria-hidden /> : <Bot className="size-3.5" aria-hidden />}
                    {m.role === "owner" ? "Chị trả lời" : "Trợ lý AI"}
                  </span>
                ) : null}
                <p className="whitespace-pre-line">{m.content}</p>
                {m.citations.length ? (
                  <p className="mt-1.5 text-[12.5px] text-ink-2">
                    Nguồn: {m.citations.map((c) => c.label).join(" · ")}
                  </p>
                ) : null}
              </div>
              {m.role === "assistant" && m.unknown ? <Badge tone="accent">Đã chuyển cho chị</Badge> : null}
              {m.role === "assistant" && !m.unknown ? (
                <span className="flex gap-0.5">
                  <IconButton
                    label="Câu trả lời có ích"
                    size="sm"
                    variant="ghost"
                    icon={<ThumbsUp className={cn(m.feedback === "up" && "fill-current text-accent")} />}
                    onClick={() => rate(m, "up")}
                  />
                  <IconButton
                    label="Câu trả lời chưa đúng"
                    size="sm"
                    variant="ghost"
                    icon={<ThumbsDown className={cn(m.feedback === "down" && "fill-current text-seal")} />}
                    onClick={() => rate(m, "down")}
                  />
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      ) : suggestions.length ? (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => ask(s)}
              className="rounded-md border border-line-strong bg-surface px-3 py-1.5 text-left text-[14px] hover:border-ink-3"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      {handedOff && conv && !conv.contact_saved ? (
        <form onSubmit={saveContact} className="flex flex-col gap-2 rounded-md border border-line bg-surface p-3">
          <p className="text-[14px] text-ink-2">Muốn chị nhắn lại? Để lại số điện thoại hoặc Zalo (không bắt buộc).</p>
          <div className="flex gap-2">
            <Input
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              placeholder="Số điện thoại / Zalo"
              aria-label="Số điện thoại hoặc Zalo"
              inputMode="tel"
              wrapperClassName="flex-1"
              maxLength={200}
            />
            <Button type="submit" variant="secondary" disabled={contact.trim().length < 6}>
              Lưu
            </Button>
          </div>
        </form>
      ) : null}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="flex gap-2"
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={placeholder ?? (productName ? "Hỏi về món này…" : "Nhập câu hỏi…")}
          aria-label={productName ? `Câu hỏi về ${productName}` : "Câu hỏi"}
          wrapperClassName="flex-1"
          maxLength={500}
          enterKeyHint="send"
          trailing={<CornerDownLeft className="hidden md:block" aria-hidden />}
        />
        <Button type="submit" loading={sending} disabled={!question.trim()} icon={<Send className="size-4" />} aria-label="Gửi câu hỏi">
          <span className="sr-only md:not-sr-only">Hỏi</span>
        </Button>
      </form>
      {error ? (
        <p role="alert" className="text-[14px] text-seal">
          {error}
        </p>
      ) : null}
      <p className="text-[12.5px] text-ink-3">Trợ lý là AI, chỉ trả lời dựa trên hồ sơ thẩm định của chị. Không chắc thì chuyển cho chị.</p>
    </section>
  );
}
