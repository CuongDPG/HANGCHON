"use client";

/**
 * API của trung tâm điều khiển (backend `app/modules/control`): «Hôm nay», hàng chờ duyệt, mức tự chủ, nhật ký AI,
 * chi phí AI, cài đặt, lưu vết, lệnh bằng lời, tài khoản phụ giúp.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";
import type { SessionUser } from "./auth";

/* ---------- kiểu dữ liệu ---------- */

export type AutonomyLevel = "auto" | "ask" | "off" | "locked_ask";
export type ApprovalStatus = "pending" | "approved" | "returned" | "failed" | "cancelled" | "expired";

export type Source = { url?: string; title?: string } & Record<string, unknown>;

/** Quy ước `preview` (module nào cũng dùng được): những khoá này hiện đẹp, khoá khác hiện dạng nhãn — giá trị. */
export type Preview = {
  kind?: string;
  /** Nội dung chính: bài viết, tin nhắn. */
  text?: string;
  channel?: string;
  image_url?: string;
  images?: string[];
  /** Dòng nhãn — giá trị; `format: "vnd"` để hiện tiền. */
  fields?: { label: string; value: unknown; format?: "vnd" | "number" | "text" }[];
  /** Danh sách gạch đầu dòng. */
  list?: string[];
  /** Dòng hàng (hoá đơn, đơn đặt). */
  lines?: { name?: string; description?: string; quantity: number; unit_price_vnd?: number; unit_price_amount?: number; unit?: string }[];
  total_vnd?: number;
  /** Trang chi tiết trên bàn làm việc để xem kỹ hơn. */
  href?: string;
} & Record<string, unknown>;

export type ApprovalItem = {
  id: string;
  /** Màn hình của đối tượng liên quan (máy chủ tính), vd /desk/don-hang/<id>. */
  href?: string | null;
  action: string;
  action_label: string;
  action_group: string | null;
  locked: boolean;
  module: string;
  title: string;
  summary: string | null;
  payload: Record<string, unknown>;
  preview: Preview;
  edited_payload: Record<string, unknown> | null;
  was_edited: boolean;
  status: ApprovalStatus;
  priority: number;
  rationale: string | null;
  sources: Source[];
  ref_type: string | null;
  ref_id: string | null;
  ai_generated: boolean;
  ai_run_id: string | null;
  decision_note: string | null;
  decided_at: string | null;
  decided_by_id: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  created_at: string;
  updated_at: string;
};

export type Activity = {
  id: string;
  href?: string | null;
  action: string;
  action_label: string;
  module: string;
  title: string;
  summary: string | null;
  mode: "auto" | "approved";
  rationale: string | null;
  sources: Source[];
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  ref_type: string | null;
  ref_id: string | null;
  approval_item_id: string | null;
  ai_run_id: string | null;
  undoable: boolean;
  undone_at: string | null;
  undone_by_id: string | null;
  created_at: string;
};

export type Stat = {
  key: string;
  label: string;
  value: number | string;
  format: "number" | "vnd" | "percent" | "text";
  hint: string | null;
  href: string | null;
  order: number;
};

export type Today = {
  date: string;
  pending: { total: number; items: ApprovalItem[] };
  ai_done: { total: number; items: Activity[]; auto_total: number; groups: { action: string; label: string; count: number }[] };
  stats: Stat[];
  ai_cost: { month: string; spent_vnd: number; budget_vnd: number; used_pct: number };
};

export type ApprovalGroup = { action: string; label: string; group: string | null; locked: boolean; count: number };

export type AutonomyRow = {
  action: string;
  label: string;
  group: string;
  description: string;
  module: string;
  level: AutonomyLevel;
  default_level: AutonomyLevel;
  locked: boolean;
  customer_facing: boolean;
  updated_at: string | null;
  history: { approved: number; edited: number; returned: number; streak: number };
  suggest_auto: boolean;
};

export type AICosts = {
  month: string;
  spent_vnd: number;
  budget_vnd: number;
  remaining_vnd: number;
  used_pct: number;
  run_count: number;
  error_count: number;
  blocked_count: number;
  by_task: { task: string; label: string; runs: number; cost_vnd: number; input_tokens: number; output_tokens: number }[];
  by_day: { date: string; runs: number; cost_vnd: number }[];
};

export type Setting = {
  key: string;
  label: string;
  group: string;
  description: string;
  default: unknown;
  value: unknown;
  is_default: boolean;
  updated_at: string | null;
};

export type AuditEntry = {
  id: string;
  created_at: string;
  actor_kind: "owner" | "helper" | "ai" | "system" | "customer";
  actor_user_id: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string | null;
  data: Record<string, unknown>;
};

export type Integration = {
  kind: string;
  label: string;
  driver: string;
  /** mọi kênh đều giả lập */
  is_mock: boolean;
  /** có kênh thật, có kênh còn giả lập */
  partly_mock: boolean;
  drivers: string[];
  /** giả lập nghĩa là gì với chị (vd tin không tới khách) */
  mock_effect: string | null;
  /** bản chạy thật từ chối dùng driver giả này (hoá đơn điện tử) */
  blocked_in_prod: boolean;
  available: string[];
};

/** Nguồn cấu hình AI: `settings` = chị lưu ở Cài đặt, `env` = biến môi trường / mặc định của máy chủ. */
export type AIConfigSource = "settings" | "env";
export type AIEffort = "low" | "medium" | "high" | "max";

export type AIProviderInfo = {
  name: string;
  label: string;
  needs_key: boolean;
  supports_web: boolean;
  needs_base_url: boolean;
  default_base_url: string | null;
  model_suggestions: string[];
  key_placeholder: string;
  saved: boolean;
  has_key: boolean;
  /** Dạng che (vd `sk-ant-…8AAA`) — API không bao giờ trả khoá thật. */
  key_hint: string | null;
  key_source: AIConfigSource | null;
  key_updated_at: string | null;
  key_updated_by: string | null;
  base_url: string | null;
  model_smart: string;
  model_fast: string;
  effort_smart: string | null;
  effort_fast: string | null;
};

export type AIConfig = {
  provider: string;
  source: AIConfigSource;
  providers: AIProviderInfo[];
  efforts: AIEffort[];
  monthly_budget_vnd: number;
  budget_source: AIConfigSource;
};

export type AIConfigInput = {
  provider: string;
  /** Để trống = giữ khoá đã lưu. */
  api_key?: string | null;
  base_url?: string | null;
  model_smart?: string | null;
  model_fast?: string | null;
  effort_smart?: AIEffort | null;
  effort_fast?: AIEffort | null;
  monthly_budget_vnd?: number | null;
  /** Lưu xong chuyển sang dùng provider này (mặc định có). */
  activate?: boolean;
};

export type AITestResult = {
  tier: "fast" | "smart";
  ok: boolean;
  model: string;
  latency_ms: number;
  cost_vnd: number;
  error: string | null;
  code: string | null;
};

export type Intent = { key: string; label: string; description: string; examples: string[] };

export type CommandResult = {
  text: string;
  /** pending = đã đưa vào hàng chờ, chờ chị duyệt (lệnh đổi dữ liệu theo mức tự chủ) */
  status: "done" | "pending" | "needs_clarification" | "unknown" | "failed";
  intent: string | null;
  label: string | null;
  message: string;
  href: string | null;
  data: Record<string, unknown> | null;
};

export type BatchResult = { approved: number; failed: number; results: { id: string; status: ApprovalStatus | null; error: string | null }[] };

/* ---------- khoá truy vấn ---------- */

const BASE = "/api/desk/control";

export const controlKeys = {
  all: ["control"] as const,
  today: () => ["control", "today"] as const,
  approvals: (q: object) => ["control", "approvals", q] as const,
  approval: (id: string) => ["control", "approval", id] as const,
  groups: () => ["control", "approval-groups"] as const,
  activity: (q: object) => ["control", "activity", q] as const,
  autonomy: () => ["control", "autonomy"] as const,
  costs: (month?: string) => ["control", "ai-costs", month ?? "now"] as const,
  settings: () => ["control", "settings"] as const,
  audit: (q: object) => ["control", "audit", q] as const,
  integrations: () => ["control", "integrations"] as const,
  aiConfig: () => ["control", "ai-config"] as const,
  channels: () => ["control", "channels"] as const,
  sources: () => ["control", "sources"] as const,
  intents: () => ["control", "intents"] as const,
  users: () => ["control", "users"] as const,
};

/** Duyệt / hoàn tác / đổi mức làm thay đổi nhiều khối cùng lúc: làm mới cả nhóm control (và số liệu finance). */
function useInvalidateControl() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: controlKeys.all });
    void qc.invalidateQueries({ queryKey: ["finance"] });
  };
}

/* ---------- Hôm nay (i1) ---------- */

export function useToday() {
  return useQuery({ queryKey: controlKeys.today(), queryFn: () => api.get<Today>(`${BASE}/today`), refetchInterval: 60_000 });
}

/* ---------- hàng chờ duyệt (i2) ---------- */

export type ApprovalQuery = { status?: ApprovalStatus[]; action?: string; page?: number; size?: number };

export function useApprovals(query: ApprovalQuery = {}) {
  return useQuery({
    queryKey: controlKeys.approvals(query),
    queryFn: () => api.get<Paginated<ApprovalItem>>(`${BASE}/approvals`, { query: { ...query, size: query.size ?? 50 } }),
    placeholderData: keepPreviousData,
  });
}

export function useApproval(id: string | null) {
  return useQuery({
    queryKey: controlKeys.approval(id ?? ""),
    queryFn: () => api.get<ApprovalItem>(`${BASE}/approvals/${id}`),
    enabled: !!id,
  });
}

export function useApprovalGroups() {
  return useQuery({ queryKey: controlKeys.groups(), queryFn: () => api.get<ApprovalGroup[]>(`${BASE}/approvals/groups`) });
}

export function useApprove() {
  const invalidate = useInvalidateControl();
  return useMutation({
    mutationFn: ({ id, payload, note }: { id: string; payload?: Record<string, unknown>; note?: string }) =>
      api.post<ApprovalItem>(`${BASE}/approvals/${id}/approve`, { payload: payload ?? null, note: note ?? null }),
    onSuccess: invalidate,
  });
}

export function useReturnApproval() {
  const invalidate = useInvalidateControl();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => api.post<ApprovalItem>(`${BASE}/approvals/${id}/return`, { note }),
    onSuccess: invalidate,
  });
}

export function useApproveBatch() {
  const invalidate = useInvalidateControl();
  return useMutation({
    mutationFn: (ids: string[]) => api.post<BatchResult>(`${BASE}/approvals/approve-batch`, { ids }),
    onSuccess: invalidate,
  });
}

/* ---------- nhật ký AI (i4) ---------- */

export type ActivityQuery = { module?: string; action?: string; mode?: "auto" | "approved"; date_from?: string; date_to?: string; page?: number };

export function useActivity(query: ActivityQuery) {
  return useQuery({
    queryKey: controlKeys.activity(query),
    queryFn: () => api.get<Paginated<Activity>>(`${BASE}/activity`, { query: { ...query, size: 30 } }),
    placeholderData: keepPreviousData,
  });
}

export function useUndo() {
  const invalidate = useInvalidateControl();
  return useMutation({
    mutationFn: (id: string) => api.post<Activity>(`${BASE}/activity/${id}/undo`),
    onSuccess: invalidate,
  });
}

/* ---------- mức tự chủ (i3) ---------- */

export function useAutonomy() {
  return useQuery({ queryKey: controlKeys.autonomy(), queryFn: () => api.get<AutonomyRow[]>(`${BASE}/autonomy`) });
}

export function useSetAutonomy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ action, level }: { action: string; level: "auto" | "ask" | "off" }) =>
      api.patch<AutonomyRow>(`${BASE}/autonomy/${encodeURIComponent(action)}`, { level }),
    onMutate: async ({ action, level }) => {
      await qc.cancelQueries({ queryKey: controlKeys.autonomy() });
      const prev = qc.getQueryData<AutonomyRow[]>(controlKeys.autonomy());
      qc.setQueryData<AutonomyRow[]>(controlKeys.autonomy(), (rows) =>
        rows?.map((r) => (r.action === action ? { ...r, level, suggest_auto: false } : r)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(controlKeys.autonomy(), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: controlKeys.autonomy() }),
  });
}

/* ---------- chi phí AI (k2) ---------- */

export function useAICosts(month?: string) {
  return useQuery({
    queryKey: controlKeys.costs(month),
    queryFn: () => api.get<AICosts>(`${BASE}/ai/costs`, { query: { month } }),
    placeholderData: keepPreviousData,
  });
}

export function useSetBudget() {
  const invalidate = useInvalidateControl();
  return useMutation({
    mutationFn: (monthly_budget_vnd: number) => api.patch<AICosts>(`${BASE}/ai/budget`, { monthly_budget_vnd }),
    onSuccess: invalidate,
  });
}

/* ---------- cài đặt, lưu vết, tích hợp (k3, k4) ---------- */

export function useSettings() {
  return useQuery({ queryKey: controlKeys.settings(), queryFn: () => api.get<Setting[]>(`${BASE}/settings`) });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => api.patch<Setting[]>(`${BASE}/settings`, { values }),
    onSuccess: (rows) => qc.setQueryData(controlKeys.settings(), rows),
  });
}

export function useAudit(query: { actions?: string[]; page?: number }, enabled = true) {
  return useQuery({
    queryKey: controlKeys.audit(query),
    queryFn: () => api.get<Paginated<AuditEntry>>(`${BASE}/audit`, { query: { ...query, size: 30 } }),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useIntegrations() {
  return useQuery({ queryKey: controlKeys.integrations(), queryFn: () => api.get<Integration[]>(`${BASE}/integrations`) });
}

/* ---------- tài khoản kênh: Cài đặt → Mạng xã hội (chỉ chị) ---------- */

export type ChannelField = {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  /** do nút «Kết nối» điền */
  oauth: boolean;
  hint: string;
  /** chỉ có với ô không bí mật */
  value: string | null;
  /** bí mật: chỉ 4 ký tự cuối */
  masked: string | null;
  is_set: boolean;
  source: "settings" | "env" | null;
};

export type ChannelAccount = {
  channel: string;
  label: string;
  kind: "social" | "marketplaces" | "manual";
  driver: string;
  mode: "mock" | "real";
  mode_source: "settings" | "env";
  status: "manual" | "mock" | "connected" | "not_connected";
  ready: boolean;
  account_name: string | null;
  fields: ChannelField[];
  shared: { channel: string; key: string; label: string; is_set: boolean }[];
  check: { ok: boolean; message: string; account_name: string | null; at: string | null } | null;
  oauth: { supported: boolean; redirect_uri: string | null; connected: boolean; expires_at: number | null; refresh_expires_at: number | null };
  guide: { needs: string[]; steps: string[]; limits: string[]; links: { label: string; url: string }[] };
};

export type ChannelAccountInput = { mode?: "mock" | "real"; values?: Record<string, string>; clear?: string[] };

export function useChannelAccounts(enabled: boolean) {
  return useQuery({ queryKey: controlKeys.channels(), queryFn: () => api.get<ChannelAccount[]>(`${BASE}/channels`), enabled });
}

function useChannelsInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: controlKeys.channels() });
    void qc.invalidateQueries({ queryKey: controlKeys.integrations() });
  };
}

export function useSaveChannelAccount() {
  const done = useChannelsInvalidate();
  return useMutation({
    mutationFn: ({ channel, ...input }: ChannelAccountInput & { channel: string }) => api.patch<ChannelAccount>(`${BASE}/channels/${channel}`, input),
    onSuccess: done,
  });
}

export function useCheckChannelAccount() {
  const done = useChannelsInvalidate();
  return useMutation({
    mutationFn: ({ channel, values }: { channel: string; values?: Record<string, string> }) =>
      api.post<{ ok: boolean; message: string; account_name: string | null }>(`${BASE}/channels/${channel}/check`, { values: values ?? {} }),
    onSuccess: done,
  });
}

export function useConnectChannelAccount() {
  return useMutation({
    mutationFn: (channel: string) => api.post<{ url: string; redirect_uri: string }>(`${BASE}/channels/${channel}/connect`),
  });
}

/* ---------- nguồn hàng: Cài đặt → Nguồn hàng (chỉ chị) ---------- */

export type SourcePlatformCard = {
  platform: string;
  label: string;
  /** mock | web | onebound | rakuten */
  driver: string;
  driver_source: "settings" | "env";
  status: "mock" | "web" | "connected" | "not_connected";
  account: string | null;
  options: { driver: string; label: string }[];
  notes: string[];
  warning: string | null;
};

export type SourceAccount = {
  account: string;
  label: string;
  driver: string;
  platforms: string[];
  used_by: string[];
  ready: boolean;
  verified: boolean;
  fields: ChannelField[];
  check: { ok: boolean; message: string; at: string | null } | null;
  guide: { needs: string[]; steps: string[]; limits: string[]; cost: string[]; links: { label: string; url: string }[] };
};

export type SourcesOverview = { platforms: SourcePlatformCard[]; accounts: SourceAccount[]; general_driver: string };

export function useSources(enabled: boolean) {
  return useQuery({ queryKey: controlKeys.sources(), queryFn: () => api.get<SourcesOverview>(`${BASE}/sources`), enabled });
}

function useSourcesInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: controlKeys.sources() });
    void qc.invalidateQueries({ queryKey: controlKeys.integrations() });
  };
}

export function useSaveSourceRoute() {
  const done = useSourcesInvalidate();
  return useMutation({
    mutationFn: ({ platform, driver }: { platform: string; driver: string | null }) =>
      api.patch<SourcesOverview>(`${BASE}/sources/platforms/${platform}`, { driver }),
    onSuccess: done,
  });
}

export function useSaveSourceAccount() {
  const done = useSourcesInvalidate();
  return useMutation({
    mutationFn: ({ account, ...input }: { account: string; values?: Record<string, string>; clear?: string[] }) =>
      api.patch<SourceAccount>(`${BASE}/sources/accounts/${account}`, input),
    onSuccess: done,
  });
}

export function useCheckSourceAccount() {
  const done = useSourcesInvalidate();
  return useMutation({
    mutationFn: ({ account, values }: { account: string; values?: Record<string, string> }) =>
      api.post<{ ok: boolean; message: string }>(`${BASE}/sources/accounts/${account}/check`, { values: values ?? {} }),
    onSuccess: done,
  });
}

/* ---------- cấu hình AI: nhà cung cấp, khoá API, model (chỉ chị) ---------- */

export function useAIConfig(enabled: boolean) {
  return useQuery({ queryKey: controlKeys.aiConfig(), queryFn: () => api.get<AIConfig>(`${BASE}/ai/config`), enabled });
}

export function useSaveAIConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: AIConfigInput) => api.patch<AIConfig>(`${BASE}/ai/config`, input),
    onSuccess: (cfg) => {
      qc.setQueryData(controlKeys.aiConfig(), cfg);
      qc.invalidateQueries({ queryKey: ["control", "ai-costs"] });
    },
  });
}

/** Gửi một lệnh rất ngắn tới từng tầng bằng cấu hình đang nhập (chưa lưu). Gọi thật, tính phí như lượt thường. */
export function useTestAIConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: AIConfigInput) => api.post<{ provider: string; results: AITestResult[] }>(`${BASE}/ai/config/test`, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["control", "ai-costs"] }),
  });
}

export function useClearAIKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: string) => api.delete<void>(`${BASE}/ai/config/${encodeURIComponent(provider)}/key`),
    onSuccess: () => qc.invalidateQueries({ queryKey: controlKeys.aiConfig() }),
  });
}

/* ---------- lệnh bằng lời (i6) ---------- */

export function useIntents(enabled: boolean) {
  return useQuery({
    queryKey: controlKeys.intents(),
    queryFn: () => api.get<Intent[]>(`${BASE}/commands`),
    enabled,
    staleTime: 10 * 60_000,
  });
}

export function useCommand() {
  const invalidate = useInvalidateControl();
  return useMutation({
    mutationFn: (input: { text: string; context?: Record<string, unknown> }) =>
      api.post<CommandResult>(`${BASE}/command`, { text: input.text, context: input.context ?? {} }),
    meta: { silentError: true },
    onSuccess: invalidate,
  });
}

/* ---------- người phụ giúp (k4) ---------- */

export function useUsers(enabled: boolean) {
  return useQuery({ queryKey: controlKeys.users(), queryFn: () => api.get<SessionUser[]>("/api/desk/users"), enabled });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { email: string; name: string; password: string }) =>
      api.post<SessionUser>("/api/desk/users", { ...input, role: "helper" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: controlKeys.users() }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; password?: string; is_active?: boolean }) =>
      api.patch<SessionUser>(`/api/desk/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: controlKeys.users() }),
  });
}

/* ---------- nhãn dùng chung ---------- */

/** Tên tiếng Việt của module backend (lọc nhật ký, nhãn nhóm). */
export const MODULE_LABELS: Record<string, string> = {
  control: "Hệ thống",
  sourcing: "Săn hàng",
  assessment: "Thẩm định",
  selection: "Bàn chọn",
  supply: "Nguồn cung",
  catalog: "Sản phẩm",
  orders: "Đơn hàng",
  assistant: "Trợ lý web",
  content: "Nội dung",
  inbox: "Hộp thư",
  crm: "Khách",
  finance: "Sổ sách",
  demo: "Mẫu",
};

export function moduleLabel(m: string): string {
  return MODULE_LABELS[m] ?? m;
}
