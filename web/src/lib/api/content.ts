"use client";

/**
 * Xưởng nội dung (f1–f8): bản nháp theo kênh, soát lời, lịch đăng, số liệu bài, giọng của chị, video ngắn, livestream.
 * Backend: /api/desk/content/** (module content).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

export type ContentChannel = "facebook" | "instagram" | "threads" | "tiktok" | "zalo_oa";
export type DraftStatus = "drafting" | "pending_review" | "approved" | "returned" | "scheduled" | "published" | "archived";
export type CheckStatus = "unchecked" | "passed" | "warnings" | "failed";
export type PostStatus = "planned" | "approved" | "publishing" | "published" | "draft_pushed" | "failed" | "cancelled" | "hidden" | "removed";
export type DisplayStatus = "published" | "draft_pushed" | "approved" | "pending" | "needs_fix" | "failed" | "publishing" | "hidden" | "removed";

export type CheckFinding = {
  key: "numbers" | "claims" | "length" | "voice" | "process" | "reason" | "safety" | "ai_label";
  label: string;
  ok: boolean;
  detail: string;
  suggestion: string | null;
  overridden?: boolean;
  override_reason?: string;
};

export type Scene = { scene: number; seconds: number; visual: string; voiceover: string; on_screen_text: string };

export type ScheduledPost = {
  id: string;
  draft_id: string;
  channel: ContentChannel;
  scheduled_at: string;
  status: PostStatus;
  published_at: string | null;
  external_post_id: string | null;
  external_url: string | null;
  attempts: number;
  error: string | null;
};

export type MediaAsset = {
  id: string;
  kind: "image" | "video" | "audio";
  purpose: "trial_clip" | "edited_video" | (string & {});
  status: "uploaded" | "processing" | "ready" | "pending_review" | "approved" | "failed";
  storage_key: string;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  product_id: string | null;
  parent_asset_id: string | null;
  edit_spec: VideoSpec & Record<string, unknown>;
  transcript: string | null;
  ai_generated: boolean;
  created_at: string;
  url: string | null;
  product_name: string | null;
};

export type VideoSpec = {
  summary?: string;
  segments?: { clip_id: string; start: number; end: number; caption: string }[];
  music?: { mood: string; suggestion: string; bpm: number | null };
  cover_text?: string;
  render?: "queued" | "done" | "unavailable" | "failed";
  render_note?: string | null;
  total_seconds?: number;
};

export type Draft = {
  id: string;
  product_id: string | null;
  drop_id: string | null;
  channel: ContentChannel;
  channel_label: string;
  format: "post" | "carousel" | "reel" | "video_script" | "zalo_message" | "story";
  status: DraftStatus;
  title: string | null;
  body: string;
  hashtags: string[];
  script: Record<string, unknown>[];
  link_url: string | null;
  version: number;
  parent_draft_id: string | null;
  check_status: CheckStatus;
  check_findings: CheckFinding[];
  ai_generated: boolean;
  feedback_note: string | null;
  can_approve: boolean;
  post: ScheduledPost | null;
  src_code: string | null;
  approval_item_id_pending: string | null;
  slides: { image_index: number; caption: string; image_url: string | null }[];
  video: MediaAsset | null;
  video_url: string | null;
  updated_at: string;
};

export type StudioItem = {
  kind: "product" | "drop";
  id: string;
  name: string;
  subtitle: string | null;
  image_url: string | null;
  status: string;
  total: number;
  approved: number;
  drafting: number;
  needs_fix: number;
  pending: number;
  updated_at: string;
};

export type StudioDetail = {
  kind: "product" | "drop";
  id: string;
  name: string;
  subtitle: string | null;
  price_vnd: number | null;
  image_url: string | null;
  image_urls: string[];
  url: string;
  reason_selected: string | null;
  not_satisfied: string | null;
  trial_days: number | null;
  considered_count: number | null;
  drop: { id: string; code: string; title: string; closes_at: string | null } | null;
  drafts: Draft[];
  compose_pending: boolean;
  /** Trạng thái trang sản phẩm trên website (chỉ với `kind: "product"`). */
  page_status?: string | null;
  candidate_id?: string | null;
};

export type PostCard = {
  id: string;
  draft_id: string;
  channel: ContentChannel;
  channel_label: string;
  scheduled_at: string;
  published_at: string | null;
  status: PostStatus;
  display_status: DisplayStatus;
  title: string;
  product_id: string | null;
  drop_id: string | null;
  name: string | null;
  external_url: string | null;
  error: string | null;
  attempts: number;
  approval_item_id: string | null;
  src_code: string;
  orders: number;
};

export type SlotSuggestion = {
  id: string;
  slot_at: string;
  channel: ContentChannel | null;
  channel_label: string;
  product_id: string | null;
  name: string | null;
  idea: string | null;
  reason: string | null;
};

export type CalendarDay = {
  day: string;
  label: string;
  name: string;
  rest: boolean;
  posts: PostCard[];
  suggestions: SlotSuggestion[];
};

export type CalendarWeek = {
  week_start: string;
  label: string;
  days: CalendarDay[];
  counts: Partial<Record<DisplayStatus, number>>;
  best_times: { channel: ContentChannel; channel_label: string; time: string; source: "default" | "metrics" }[];
};

export type Insight = {
  id: string;
  period_start: string;
  period_end: string;
  summary: string;
  findings: { pattern: string; evidence: string; recommendation: string }[];
  top_post_ids: string[];
  created_at: string;
};

export type PerformanceRow = {
  scheduled_post_id: string;
  channel: ContentChannel;
  channel_label: string;
  status: string;
  title: string;
  name: string | null;
  product_id: string | null;
  published_at: string;
  external_url: string | null;
  src_code: string;
  reach: number;
  likes: number;
  comments: number;
  shares: number;
  clicks: number;
  video_views: number;
  orders: number;
  revenue_vnd: number;
  measured_at: string | null;
};

export type Performance = {
  days: number;
  posts: PerformanceRow[];
  totals: { posts: number; orders: number; revenue_vnd: number; reach: number };
  insight: Insight | null;
};

export type Voice = {
  id: string;
  name: string;
  style_summary: string | null;
  pronouns: string | null;
  sentence_style: string | null;
  rules: string[];
  avoid: string[];
  vocabulary: string[];
  examples: string[];
  samples_count: number;
  samples: string[];
  version: number;
  trained_at: string | null;
  updated_at: string;
};

export type VoicePatch = Partial<Pick<Voice, "style_summary" | "pronouns" | "sentence_style" | "rules" | "avoid" | "vocabulary" | "examples">>;

export type Livestream = {
  id: string;
  title: string;
  scheduled_for: string | null;
  drop_id: string | null;
  drop_title: string | null;
  status: "drafting" | "pending_review" | "approved" | "used";
  outline: { segment: string; minutes: number; notes: string }[];
  items: { product_id: string; order: number; name: string; talking_points: string[]; demo: string; price_note: string }[];
  faq: { q: string; a: string; product_id: string | null; source: "khach_hoi" | "du_doan"; needs_review?: boolean }[];
  notes: string | null;
  ai_generated: boolean;
  approval_pending: boolean;
  created_at: string;
};

export type PickProduct = { id: string; name: string; price_vnd: number; image_url: string | null };
export type PickDrop = { id: string; code: string; title: string; status: string };

const B = "/api/desk/content";

export const contentKeys = {
  all: ["content"] as const,
  studio: () => ["content", "studio"] as const,
  detail: (kind: string, id: string) => ["content", "detail", kind, id] as const,
  calendar: (week?: string) => ["content", "calendar", week ?? "now"] as const,
  performance: () => ["content", "performance"] as const,
  voice: () => ["content", "voice"] as const,
  media: () => ["content", "media"] as const,
  livestreams: () => ["content", "livestreams"] as const,
  livestream: (id: string) => ["content", "livestream", id] as const,
  pick: (what: string) => ["content", "pick", what] as const,
};

/**
 * Dùng làm `onSuccess` của mutation: trả promise để mutation chỉ xong (hết `isPending`, rồi mới tới toast của màn hình)
 * khi dữ liệu Nội dung đã tải lại. Viết lại / sửa tay sinh bản nháp MỚI (id khác); nếu báo xong sớm, màn hình còn bản cũ
 * vài trăm ms — chị kịp mở «Duyệt, xếp lịch» trên bản cũ rồi hộp bị gỡ khi bản mới về.
 */
function useInvalidateContent() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["control"] });
    return qc.invalidateQueries({ queryKey: contentKeys.all });
  };
}

// ---- xưởng ----------------------------------------------------------------------------------------------------

export function useStudio() {
  return useQuery({ queryKey: contentKeys.studio(), queryFn: () => api.get<Paginated<StudioItem>>(`${B}/studio`) });
}

export function useStudioDetail(kind: "product" | "drop", id: string) {
  return useQuery({
    queryKey: contentKeys.detail(kind, id),
    queryFn: () => api.get<StudioDetail>(`${B}/studio/${kind}/${id}`),
    // AI đang soạn → tự tải lại cho tới khi xong
    refetchInterval: (q) => (q.state.data?.compose_pending ? 4000 : false),
  });
}

export function useCompose(kind: "product" | "drop", id: string) {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: (body: { channels?: ContentChannel[]; instruction?: string }) =>
      api.post<StudioDetail>(`${B}/studio/${kind}/${id}/compose`, body),
    onSuccess: inv,
  });
}

export function useEditDraft() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; title?: string | null; body?: string; hashtags?: string[]; script?: Record<string, unknown>[] }) =>
      api.patch<Draft>(`${B}/drafts/${id}`, body),
    onSuccess: inv,
  });
}

export type RewritePreset = "shorter" | "warmer" | "price";

export function useRewriteDraft() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, preset, instruction }: { id: string; preset?: RewritePreset; instruction?: string }) =>
      api.post<{ status: string; draft: Draft }>(`${B}/drafts/${id}/rewrite`, { preset, instruction }),
    onSuccess: inv,
  });
}

export function useOverrideCheck() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, key, reason }: { id: string; key: string; reason: string }) =>
      api.post<Draft>(`${B}/drafts/${id}/override`, { key, reason }),
    onSuccess: inv,
  });
}

export function useApproveDraft() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, scheduled_at }: { id: string; scheduled_at?: string | null }) =>
      api.post<Draft>(`${B}/drafts/${id}/approve`, { scheduled_at: scheduled_at ?? null }),
    onSuccess: inv,
  });
}

export function useRecheckDraft() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: (id: string) => api.post<Draft>(`${B}/drafts/${id}/recheck`), onSuccess: inv });
}

// ---- lịch + đăng -----------------------------------------------------------------------------------------------

export function useCalendar(week?: string) {
  return useQuery({
    queryKey: contentKeys.calendar(week),
    queryFn: () => api.get<CalendarWeek>(`${B}/calendar`, { query: { week } }),
  });
}

export function usePlanWeek() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: (week?: string) => api.post<{ moved: number; suggested: number; week_start: string }>(`${B}/calendar/plan`, { week: week ?? null }),
    onSuccess: inv,
  });
}

export function useAcceptSuggestion() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: (id: string) => api.post<CalendarWeek>(`${B}/calendar/suggestions/${id}/accept`), onSuccess: inv });
}

export function useDismissSuggestion() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: (id: string) => api.post<void>(`${B}/calendar/suggestions/${id}/dismiss`), onSuccess: inv });
}

export function useReschedule() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, scheduled_at }: { id: string; scheduled_at: string }) => api.patch<PostCard>(`${B}/posts/${id}`, { scheduled_at }),
    onSuccess: inv,
  });
}

export function usePostAction() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, action, url }: { id: string; action: "cancel" | "mark-published" | "publish-now"; url?: string }) =>
      api.post<PostCard>(`${B}/posts/${id}/${action}`, action === "mark-published" ? { url: url || null } : undefined),
    onSuccess: inv,
  });
}

// ---- đo và học -------------------------------------------------------------------------------------------------

export function usePerformance() {
  return useQuery({ queryKey: contentKeys.performance(), queryFn: () => api.get<Performance>(`${B}/performance`) });
}

export function useRefreshMetrics() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: () => api.post<Performance>(`${B}/performance/refresh`), onSuccess: inv });
}

export function useRunInsights() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: () => api.post<Insight>(`${B}/insights/run`), onSuccess: inv });
}

// ---- giọng -----------------------------------------------------------------------------------------------------

export function useVoice() {
  return useQuery({ queryKey: contentKeys.voice(), queryFn: () => api.get<Voice>(`${B}/voice`) });
}

export function useEditVoice() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: (body: VoicePatch) => api.patch<Voice>(`${B}/voice`, body), onSuccess: inv });
}

export function useLearnVoice() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: (body: { samples: string[]; notes?: string; spoken?: string[] }) => api.post<{ status: string; voice: Voice }>(`${B}/voice/learn`, body),
    onSuccess: inv,
  });
}

// ---- video -----------------------------------------------------------------------------------------------------

export function useMedia() {
  return useQuery({
    queryKey: contentKeys.media(),
    queryFn: () => api.get<Paginated<MediaAsset>>(`${B}/media`),
    refetchInterval: (q) => (q.state.data?.items.some((m) => m.status === "processing") ? 4000 : false),
  });
}

export function useUploadClip() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ file, productId, note }: { file: File; productId?: string; note?: string }) => {
      const fd = new FormData();
      fd.append("file", file);
      if (productId) fd.append("product_id", productId);
      if (note) fd.append("note", note);
      return api.post<MediaAsset>(`${B}/media`, fd);
    },
    onSuccess: inv,
  });
}

export function useDeleteMedia() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: (id: string) => api.delete(`${B}/media/${id}`), onSuccess: inv });
}

export function usePlanVideo() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: (body: { product_id?: string | null; clip_ids: string[]; notes?: string; target_seconds?: number }) =>
      api.post<MediaAsset>(`${B}/videos`, body),
    onSuccess: inv,
  });
}

export function useApproveVideo() {
  const inv = useInvalidateContent();
  return useMutation({ mutationFn: (id: string) => api.post<MediaAsset>(`${B}/videos/${id}/approve`), onSuccess: inv });
}

// ---- livestream ------------------------------------------------------------------------------------------------

export function useLivestreams() {
  return useQuery({ queryKey: contentKeys.livestreams(), queryFn: () => api.get<Paginated<Livestream>>(`${B}/livestreams`) });
}

export function useLivestream(id: string) {
  return useQuery({ queryKey: contentKeys.livestream(id), queryFn: () => api.get<Livestream>(`${B}/livestreams/${id}`) });
}

export function useCreateLivestream() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: (body: { title?: string; drop_id?: string | null; product_ids?: string[]; minutes?: number; instruction?: string }) =>
      api.post<Livestream>(`${B}/livestreams`, body),
    onSuccess: inv,
  });
}

export function useLivestreamAction() {
  const inv = useInvalidateContent();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "used" }) => api.post<Livestream>(`${B}/livestreams/${id}/${action}`),
    onSuccess: inv,
  });
}

export function usePickProducts() {
  return useQuery({ queryKey: contentKeys.pick("products"), queryFn: () => api.get<Paginated<PickProduct>>(`${B}/pick/products`) });
}

export function usePickDrops() {
  return useQuery({ queryKey: contentKeys.pick("drops"), queryFn: () => api.get<Paginated<PickDrop>>(`${B}/pick/drops`) });
}

/** Đường dẫn xem tệp trong kho (ảnh/video) qua API cùng origin. */
export function fileUrl(key: string | null | undefined): string | null {
  return key ? `/api/files/${key}` : null;
}
