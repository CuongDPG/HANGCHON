/** API trợ lý hỏi đáp (e7). Phiên ẩn danh nằm trong cookie httpOnly do API đặt; gọi từ trình duyệt. */
import { api } from "./client";

export type Citation = { type: string; id: string; ref: string; label: string; quote: string | null };

export type AssistantMessage = {
  id: string;
  role: "user" | "assistant" | "owner";
  content: string;
  citations: Citation[];
  unknown: boolean;
  feedback: "up" | "down" | null;
  created_at: string;
};

export type AssistantConversation = {
  id: string;
  status: "open" | "handed_off" | "closed";
  product_id: string | null;
  contact_saved: boolean;
  messages: AssistantMessage[];
};

export type AskResult = { conversation: AssistantConversation; answer: AssistantMessage; handed_off: boolean };

const S = "/api/store/assistant";

export const assistantApi = {
  ask: (input: { question: string; product_slug?: string | null; conversation_id?: string | null; page_path?: string }) =>
    api.post<AskResult>(`${S}/ask`, input),
  conversation: (id: string) => api.get<AssistantConversation>(`${S}/conversations/${id}`),
  contact: (id: string, contact: string) => api.post<AssistantConversation>(`${S}/conversations/${id}/contact`, { contact }),
  feedback: (id: string, messageId: string, value: "up" | "down") =>
    api.post<AssistantConversation>(`${S}/conversations/${id}/feedback`, { message_id: messageId, value }),
};

/** Khoá lưu mã cuộc trò chuyện theo món (sessionStorage) để mở lại khung hỏi vẫn thấy câu trả lời của chị. */
export function conversationStorageKey(productSlug?: string | null) {
  return `hc-asst:${productSlug ?? "_"}`;
}
