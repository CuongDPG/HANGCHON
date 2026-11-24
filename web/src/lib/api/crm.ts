"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

/** Chăm khách (h4–h8): sổ khách, khách quen, nhắc mua lại, giới thiệu bạn, khách thử hàng. Khớp `app/modules/crm`. */

export type CustomerItem = {
  id: string;
  name: string | null;
  phone: string | null;
  email: string | null;
  channels: string[];
  order_count: number;
  total_spent_vnd: number;
  last_order_at: string | null;
  is_regular: boolean;
  opted_out: boolean;
  tags: string[];
  summary: string | null;
  created_at: string;
};

export type CustomerNote = {
  id: string;
  customer_id: string;
  kind: "note" | "interest" | "preference" | "issue" | "ai_summary";
  source: "owner" | "ai";
  body: string;
  pinned: boolean;
  ref_type: string | null;
  created_at: string;
};

export type Reminder = {
  id: string;
  customer_id: string;
  product_id: string;
  order_id: string | null;
  due_on: string;
  reason: string | null;
  channel: string | null;
  message_body: string | null;
  status: "scheduled" | "pending_review" | "sent" | "skipped" | "converted" | "cancelled";
  sent_at: string | null;
  approval_item_id: string | null;
  customer_name: string | null;
  product_name: string | null;
};

export type TesterInvite = {
  id: string;
  candidate_id: string;
  candidate_title: string | null;
  customer_id: string;
  customer_name: string | null;
  status: "draft" | "invited" | "accepted" | "declined" | "sample_sent" | "feedback_received" | "closed";
  message: string | null;
  invited_at: string | null;
  responded_at: string | null;
  feedback: string | null;
  feedback_rating: number | null;
  feedback_at: string | null;
  link: string;
};

export type Referral = {
  id: string;
  code: string;
  referrer_customer_id: string;
  referrer_name?: string | null;
  is_active: boolean;
  reward_referrer_vnd: number;
  reward_referred_vnd: number;
  uses_count: number;
  rewarded_count: number;
};

export type CustomerProfile = CustomerItem & {
  default_address: Record<string, unknown>;
  first_channel: string | null;
  identities: { channel: string; external_id: string; display_name: string | null }[];
  notes: CustomerNote[];
  interests: string[];
  summary_updated_at: string | null;
  orders: { id: string; code: string; status: string; status_label: string; placed_at: string; total_vnd: number; items: { name: string; quantity: number }[] }[];
  threads: { id: string; channel: string; channel_label: string; kind: string; snippet: string | null; status: string; needs_owner: boolean; last_message_at: string | null }[];
  recent_questions: { body: string; sent_at: string; thread_id: string }[];
  referral: Referral | null;
  reminders: Reminder[];
  invites: TesterInvite[];
};

export type Broadcast = {
  id: string;
  kind: "drop_announcement" | "restock" | "general";
  title: string;
  body: string;
  status: "draft" | "pending_review" | "approved" | "scheduled" | "sending" | "sent" | "failed" | "cancelled";
  drop_id: string | null;
  drop_title: string | null;
  recipient_count: number;
  delivered_count: number;
  sent_at: string | null;
  ai_generated: boolean;
  approval_item_id: string | null;
  created_at: string;
};

export type GroupDigest = {
  id: string;
  summary: string;
  highlights: string[];
  open_questions: string[];
  product_mentions: { name: string; count: number; note?: string | null }[];
  created_at: string;
};

export type Regulars = { min_orders: number; total: number; reachable: number; items: CustomerItem[] };

export type ReorderRule = {
  product_id: string;
  name: string;
  is_consumable: boolean;
  product_days: number | null;
  category_days: number | null;
  configured_days: number | null;
  active: boolean;
  effective_days: number | null;
};

export type ReferralUse = {
  id: string;
  referral_id: string;
  referred_customer_id: string;
  order_id: string | null;
  status: "pending" | "qualified" | "rewarded" | "void";
  rewarded_at: string | null;
  created_at: string;
  code: string;
  referrer_name: string | null;
  referred_name: string | null;
  order_code: string | null;
};

export type ReferralStats = {
  codes: number;
  uses: number;
  pending: number;
  qualified: number;
  rewarded: number;
  orders_from_referrals: number;
  revenue_from_referrals_vnd: number;
  referred_customers: number;
  referred_repeat_rate: number | null;
  overall_repeat_rate: number | null;
};

export type TrialCandidate = {
  id: string;
  title: string;
  image_url: string | null;
  stage_changed_at: string | null;
  notes: { id: string; kind: string; author: string; text: string | null; recorded_at: string; trial_day: number | null }[];
  invites: TesterInvite[];
};

export type PublicInvite = {
  first_name: string;
  product_title: string;
  image_url: string | null;
  message: string | null;
  status: TesterInvite["status"];
  can_answer: boolean;
  can_feedback: boolean;
  feedback: string | null;
  feedback_rating: number | null;
};

export type CustomerSegment = "all" | "regular" | "optout" | "new";

const BASE = "/api/desk/crm";

export const crmKeys = {
  all: ["crm"] as const,
  customers: (q: object) => ["crm", "customers", q] as const,
  customer: (id: string) => ["crm", "customer", id] as const,
  regulars: ["crm", "regulars"] as const,
  broadcasts: ["crm", "broadcasts"] as const,
  digests: ["crm", "digests"] as const,
  rules: ["crm", "reorder-rules"] as const,
  reminders: (status?: string) => ["crm", "reminders", status ?? "all"] as const,
  referrals: ["crm", "referrals"] as const,
  referralUses: ["crm", "referral-uses"] as const,
  referralStats: ["crm", "referral-stats"] as const,
  testers: ["crm", "testers"] as const,
};

function useInvalidateCrm() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: crmKeys.all });
    qc.invalidateQueries({ queryKey: ["control"] });
  };
}

// ---- h4: sổ khách -------------------------------------------------------------------------------------------------

export function useCustomers(query: { q?: string; segment?: CustomerSegment; tag?: string; size?: number }) {
  return useQuery({
    queryKey: crmKeys.customers(query),
    queryFn: () =>
      api.get<Paginated<CustomerItem>>(`${BASE}/customers`, {
        query: { q: query.q || undefined, segment: query.segment ?? "all", tag: query.tag, size: query.size ?? 50 },
      }),
  });
}

export function useCustomer(id: string) {
  return useQuery({ queryKey: crmKeys.customer(id), queryFn: () => api.get<CustomerProfile>(`${BASE}/customers/${id}`) });
}

function useProfileMutation<V>(fn: (v: V) => Promise<CustomerProfile>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (p) => {
      qc.setQueryData(crmKeys.customer(p.id), p);
      qc.invalidateQueries({ queryKey: ["crm", "customers"] });
      qc.invalidateQueries({ queryKey: crmKeys.regulars });
    },
  });
}

export function useAddNote(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { body: string; kind: CustomerNote["kind"]; pinned?: boolean }) =>
      api.post<CustomerNote>(`${BASE}/customers/${customerId}/notes`, v),
    onSuccess: () => qc.invalidateQueries({ queryKey: crmKeys.customer(customerId) }),
  });
}

export function useEditNote(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; body?: string; pinned?: boolean }) =>
      api.patch<CustomerNote>(`${BASE}/notes/${v.id}`, { body: v.body, pinned: v.pinned }),
    onSuccess: () => qc.invalidateQueries({ queryKey: crmKeys.customer(customerId) }),
  });
}

export function useDeleteNote(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`${BASE}/notes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: crmKeys.customer(customerId) }),
  });
}

export function useAddTag() {
  return useProfileMutation((v: { customerId: string; tag: string }) =>
    api.post<CustomerProfile>(`${BASE}/customers/${v.customerId}/tags`, { tag: v.tag }),
  );
}

export function useRemoveTag(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tag: string) => api.delete(`${BASE}/customers/${customerId}/tags/${encodeURIComponent(tag)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.customer(customerId) });
      qc.invalidateQueries({ queryKey: ["crm", "customers"] });
    },
  });
}

export function useOptOut() {
  return useProfileMutation((v: { customerId: string; optOut: boolean }) =>
    api.post<CustomerProfile>(`${BASE}/customers/${v.customerId}/opt-out`, { opt_out: v.optOut }),
  );
}

export function useRefreshSummary() {
  return useProfileMutation((customerId: string) => api.post<CustomerProfile>(`${BASE}/customers/${customerId}/refresh-summary`));
}

export function useCreateReferral() {
  const invalidate = useInvalidateCrm();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) => api.post<CustomerProfile>(`${BASE}/customers/${customerId}/referral`),
    onSuccess: (p) => {
      qc.setQueryData(crmKeys.customer(p.id), p);
      invalidate();
    },
  });
}

// ---- h5: khách quen ----------------------------------------------------------------------------------------------

export function useRegulars() {
  return useQuery({ queryKey: crmKeys.regulars, queryFn: () => api.get<Regulars>(`${BASE}/regulars`) });
}

export function useUpdateRegularThreshold() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (minOrders: number) => api.patch<Regulars>(`${BASE}/settings`, { regular_min_orders: minOrders }),
    onSuccess: invalidate,
  });
}

export function useBroadcasts() {
  return useQuery({ queryKey: crmKeys.broadcasts, queryFn: () => api.get<Broadcast[]>(`${BASE}/broadcasts`) });
}

export function useCreateBroadcast() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { title: string; body: string }) => api.post<Broadcast>(`${BASE}/broadcasts`, v),
    onSuccess: invalidate,
  });
}

export function useSendBroadcast() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { id: string; body?: string }) => api.post<Broadcast>(`${BASE}/broadcasts/${v.id}/send`, { body: v.body }),
    onSuccess: invalidate,
  });
}

export function useCancelBroadcast() {
  const invalidate = useInvalidateCrm();
  return useMutation({ mutationFn: (id: string) => api.post<Broadcast>(`${BASE}/broadcasts/${id}/cancel`), onSuccess: invalidate });
}

export function useDigests() {
  return useQuery({ queryKey: crmKeys.digests, queryFn: () => api.get<GroupDigest[]>(`${BASE}/group-digests`) });
}

export function useCreateDigest() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (text: string) => api.post<GroupDigest>(`${BASE}/group-digests`, { text }),
    onSuccess: invalidate,
  });
}

// ---- h6: nhắc mua lại --------------------------------------------------------------------------------------------

export function useReorderRules() {
  return useQuery({ queryKey: crmKeys.rules, queryFn: () => api.get<ReorderRule[]>(`${BASE}/reorder-rules`) });
}

export function useSetReorderRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { productId: string; cycleDays: number | null; active: boolean }) =>
      api.put<ReorderRule[]>(`${BASE}/reorder-rules/${v.productId}`, { cycle_days: v.cycleDays, active: v.active }),
    onSuccess: (rules) => qc.setQueryData(crmKeys.rules, rules),
  });
}

export function useReminders(status?: Reminder["status"]) {
  return useQuery({
    queryKey: crmKeys.reminders(status),
    queryFn: () => api.get<Reminder[]>(`${BASE}/reminders`, { query: { status } }),
  });
}

export function useRunDue() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: () => api.post<{ drafted: number; skipped: number }>(`${BASE}/reminders/run-due`),
    onSuccess: invalidate,
  });
}

export function useSendReminder() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { id: string; body?: string }) => api.post<Reminder>(`${BASE}/reminders/${v.id}/send`, { body: v.body }),
    onSuccess: invalidate,
  });
}

export function useSkipReminder() {
  const invalidate = useInvalidateCrm();
  return useMutation({ mutationFn: (id: string) => api.post<Reminder>(`${BASE}/reminders/${id}/skip`), onSuccess: invalidate });
}

// ---- h7: giới thiệu bạn ------------------------------------------------------------------------------------------

export function useReferralStats() {
  return useQuery({ queryKey: crmKeys.referralStats, queryFn: () => api.get<ReferralStats>(`${BASE}/referrals/stats`) });
}

export function useReferrals() {
  return useQuery({ queryKey: crmKeys.referrals, queryFn: () => api.get<Referral[]>(`${BASE}/referrals`) });
}

export function useReferralUses() {
  return useQuery({ queryKey: crmKeys.referralUses, queryFn: () => api.get<ReferralUse[]>(`${BASE}/referrals/uses`) });
}

export function useRewardReferral() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { useId: string; note: string }) => api.post<ReferralStats>(`${BASE}/referral-uses/${v.useId}/reward`, { note: v.note }),
    onSuccess: invalidate,
  });
}

export function useVoidReferral() {
  const invalidate = useInvalidateCrm();
  return useMutation({ mutationFn: (useId: string) => api.post<ReferralStats>(`${BASE}/referral-uses/${useId}/void`), onSuccess: invalidate });
}

export function useManualReferral() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { referralId: string; customerId: string }) =>
      api.post<Referral>(`${BASE}/referrals/${v.referralId}/uses`, { customer_id: v.customerId }),
    onSuccess: invalidate,
  });
}

// ---- h8: khách thử hàng ------------------------------------------------------------------------------------------

export function useTrialCandidates() {
  return useQuery({ queryKey: crmKeys.testers, queryFn: () => api.get<TrialCandidate[]>(`${BASE}/testers/candidates`) });
}

export function useInviteTesters() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { candidateId: string; customerIds: string[]; message?: string }) =>
      api.post<TesterInvite[]>(`${BASE}/tester-invites`, { candidate_id: v.candidateId, customer_ids: v.customerIds, message: v.message || null }),
    onSuccess: invalidate,
  });
}

export function useInviteStatus() {
  const invalidate = useInvalidateCrm();
  return useMutation({
    mutationFn: (v: { id: string; status: "invited" | "sample_sent" | "closed" }) =>
      api.post<TesterInvite>(`${BASE}/tester-invites/${v.id}/status`, { status: v.status }),
    onSuccess: invalidate,
  });
}

/** Trang công khai /thu-hang/[token] (khách không đăng nhập). */
export const publicInviteApi = {
  get: (token: string) => api.get<PublicInvite>(`/api/store/crm/thu-hang/${encodeURIComponent(token)}`),
  respond: (token: string, body: { action: "accept" | "decline" | "feedback"; feedback?: string; rating?: number | null }) =>
    api.post<PublicInvite>(`/api/store/crm/thu-hang/${encodeURIComponent(token)}`, body),
};

export const INVITE_STATUS_LABEL: Record<TesterInvite["status"], string> = {
  draft: "Chưa gửi",
  invited: "Đã mời",
  accepted: "Nhận thử",
  declined: "Không nhận",
  sample_sent: "Đã gửi mẫu",
  feedback_received: "Đã gửi cảm nhận",
  closed: "Đã đóng",
};

export const REMINDER_STATUS_LABEL: Record<Reminder["status"], string> = {
  scheduled: "Đã lên lịch",
  pending_review: "Chờ chị duyệt",
  sent: "Đã nhắc",
  skipped: "Bỏ qua",
  converted: "Đã mua lại",
  cancelled: "Đã huỷ",
};
