"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

/** Hộp thư gộp (h1–h3): hội thoại mọi kênh, bản nháp AI soạn, việc chuyển chị. Khớp `app/modules/inbox`. */

export type InboxChannel = "facebook" | "instagram" | "zalo_oa" | "zalo" | "zalo_group" | "tiktok" | "web" | (string & {});
export type ThreadKind = "comment" | "direct_message" | "group" | "web_chat";
export type ThreadStatus = "open" | "needs_owner" | "waiting_customer" | "ai_handled" | "closed" | "spam";
export type InboxTab = "waiting" | "ai" | "all";

export type EscalationOption = { label: string; reply: string };

export type ReplyDraft = {
  id: string;
  kind: "instant" | "draft" | "escalation";
  intent: string | null;
  intent_label: string | null;
  body: string;
  status: string;
  confidence: string | null;
  sources: { fact?: string }[];
  options: EscalationOption[];
  approval_item_id: string | null;
  created_at: string;
};

export type LastMessage = {
  direction: "inbound" | "outbound";
  sender: "customer" | "owner" | "helper" | "ai" | "system";
  body: string;
  ai_generated: boolean;
  sent_at: string;
};

export type ThreadItem = {
  id: string;
  channel: InboxChannel;
  channel_label: string;
  kind: ThreadKind;
  participant_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  status: ThreadStatus;
  needs_owner: boolean;
  escalation_reason: string | null;
  escalation_label: string | null;
  last_intent: string | null;
  intent_label: string | null;
  snippet: string | null;
  last_message_at: string | null;
  unread_count: number;
  last_message: LastMessage | null;
  /** Tin gần nhất của khách (hiện trên thẻ hội thoại). */
  last_inbound: LastMessage | null;
  draft: ReplyDraft | null;
};

export type InboxMessage = {
  id: string;
  direction: "inbound" | "outbound";
  sender: LastMessage["sender"];
  author_name: string | null;
  body: string;
  attachments: { url?: string }[];
  sent_at: string;
  status: "received" | "queued" | "sent" | "failed";
  intent: string | null;
  ai_generated: boolean;
  extracted: Record<string, unknown>;
};

export type ThreadDetail = ThreadItem & {
  account_name: string | null;
  external_post_id: string | null;
  messages: InboxMessage[];
  customer: { id: string; name: string | null; phone: string | null; order_count: number; total_spent_vnd: number; is_regular: boolean } | null;
  product: { id: string; name: string; slug: string; price_vnd: number } | null;
  capabilities: { can_reply: boolean; reason: string | null; human_agent_tag: boolean; private_reply: boolean };
};

export type ThreadCounts = { waiting: number; ai: number; all: number };

export type ChannelAccount = { id: string; channel: InboxChannel; name: string; driver: string; status: string };
export type InboxMeta = { simulate_enabled: boolean; accounts: ChannelAccount[] };

export type SimulateInput = {
  text: string;
  channel: "facebook" | "instagram" | "zalo_oa";
  kind: "comment" | "direct_message";
  author_name: string;
};

export const inboxKeys = {
  all: ["inbox"] as const,
  threads: (q: object) => ["inbox", "threads", q] as const,
  thread: (id: string) => ["inbox", "thread", id] as const,
  counts: ["inbox", "counts"] as const,
  meta: ["inbox", "meta"] as const,
};

const BASE = "/api/desk/inbox";

export function useThreads(query: { tab: InboxTab; q?: string; size?: number }) {
  return useQuery({
    queryKey: inboxKeys.threads(query),
    queryFn: () =>
      api.get<Paginated<ThreadItem>>(`${BASE}/threads`, { query: { tab: query.tab, q: query.q || undefined, size: query.size ?? 50 } }),
    refetchInterval: 30_000,
  });
}

export function useThreadCounts() {
  return useQuery({ queryKey: inboxKeys.counts, queryFn: () => api.get<ThreadCounts>(`${BASE}/counts`), refetchInterval: 30_000 });
}

export function useThread(id: string) {
  return useQuery({ queryKey: inboxKeys.thread(id), queryFn: () => api.get<ThreadDetail>(`${BASE}/threads/${id}`) });
}

export function useInboxMeta() {
  return useQuery({ queryKey: inboxKeys.meta, queryFn: () => api.get<InboxMeta>(`${BASE}/meta`), staleTime: 5 * 60_000 });
}

/** Mọi thao tác trả về hội thoại mới nhất: ghi thẳng vào cache rồi làm mới danh sách. */
function useThreadMutation<V>(fn: (v: V) => Promise<ThreadDetail>, opts?: { silent?: boolean }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    meta: opts?.silent ? { silentError: true } : undefined,
    onSuccess: (t) => {
      qc.setQueryData(inboxKeys.thread(t.id), t);
      qc.invalidateQueries({ queryKey: ["inbox", "threads"] });
      qc.invalidateQueries({ queryKey: inboxKeys.counts });
      qc.invalidateQueries({ queryKey: ["control"] });
    },
  });
}

export function useSendDraft() {
  return useThreadMutation((v: { draftId: string; body?: string; private?: boolean }) =>
    api.post<ThreadDetail>(`${BASE}/drafts/${v.draftId}/send`, { body: v.body, private: v.private ?? false }),
  );
}

export function useDismissDraft() {
  return useThreadMutation((draftId: string) => api.post<ThreadDetail>(`${BASE}/drafts/${draftId}/dismiss`));
}

export function useReply() {
  return useThreadMutation((v: { threadId: string; body: string; private?: boolean }) =>
    api.post<ThreadDetail>(`${BASE}/threads/${v.threadId}/reply`, { body: v.body, private: v.private ?? false }),
  );
}

export function useRedraft() {
  return useThreadMutation((v: { threadId: string; note?: string }) =>
    api.post<ThreadDetail>(`${BASE}/threads/${v.threadId}/redraft`, { note: v.note || null }),
  );
}

export function useLinkCustomer() {
  return useThreadMutation((v: { threadId: string; customerId: string | null }) =>
    api.post<ThreadDetail>(`${BASE}/threads/${v.threadId}/customer`, { customer_id: v.customerId }),
  );
}

export function useThreadStatus() {
  return useThreadMutation((v: { threadId: string; status: "open" | "closed" | "spam" }) =>
    api.post<ThreadDetail>(`${BASE}/threads/${v.threadId}/status`, { status: v.status }),
  );
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => api.post<ThreadDetail>(`${BASE}/threads/${threadId}/read`),
    meta: { silentError: true },
    onSuccess: (t) => {
      qc.setQueryData(inboxKeys.thread(t.id), t);
      qc.invalidateQueries({ queryKey: ["inbox", "threads"] });
    },
  });
}

export function useSimulate() {
  return useThreadMutation((v: SimulateInput) => api.post<ThreadDetail>(`${BASE}/dev/simulate`, v));
}

/** Nhãn ngắn cho kênh khi API chưa trả `channel_label`. */
export const CHANNEL_LABEL: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  zalo_oa: "Zalo",
  zalo: "Zalo",
  zalo_group: "Nhóm Zalo",
  tiktok: "TikTok",
  web: "Website",
};
