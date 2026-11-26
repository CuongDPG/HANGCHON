"use client";

/** Săn hàng (a1–a7): đề tìm, lượt quét, ứng viên, radar xu hướng, nhu cầu khách. Backend: /api/desk/sourcing. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

const BASE = "/api/desk/sourcing";

export type BriefStatus = "draft" | "active" | "paused" | "done" | "archived";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type Origin = "cn" | "jp" | "kr" | "other";

export type BriefFilters = {
  product_type?: string | null;
  category?: string | null;
  materials?: string[];
  must?: string[];
  must_not?: string[];
  prefer?: string[];
  origins?: Origin[];
  min_rating?: number | null;
  min_reviews?: number | null;
  unclear?: string[];
  trend_signal_id?: string | null;
};

export type RunProgress = {
  step?: string;
  done?: number;
  total?: number;
  note?: string;
  candidate_ids?: string[];
  elsewhere_ids?: string[];
  brief_id?: string;
  approval_item_id?: string;
};

export type SourcingRun = {
  id: string;
  brief_id: string | null;
  kind: "brief_scan" | "link_import" | "image_search" | "scheduled_scan" | "trend_radar" | "demand_digest";
  status: RunStatus;
  platforms: string[];
  found_count: number;
  new_count: number;
  above_threshold_count: number;
  error: string | null;
  progress: RunProgress;
  created_at: string;
  finished_at: string | null;
};

export type Brief = {
  id: string;
  title: string;
  raw_text: string;
  input_mode: "text" | "voice" | "image" | "trend" | "demand";
  status: BriefStatus;
  interpretation: string | null;
  filters: BriefFilters;
  keywords_vi: string[];
  keywords_translated: { zh?: string[]; ja?: string[]; en?: string[] };
  platforms: string[];
  target_landed_cost_max_vnd: number | null;
  price_max_vnd: number | null;
  is_scheduled: boolean;
  schedule_interval_days: number | null;
  next_run_at: string | null;
  last_run_at: string | null;
  alert_min_score: number | null;
  demand_signal_id: string | null;
  find_request_id: string | null;
  candidate_count: number;
  selected_count: number;
  last_run: SourcingRun | null;
  created_at: string;
  updated_at: string;
};

export type CandidateStage = "candidate" | "sample" | "trial" | "selected" | "rejected";

export type CandidateCard = {
  id: string;
  brief_id: string | null;
  origin: string;
  stage: CandidateStage;
  source_platform: string;
  source_url: string | null;
  seller_name: string | null;
  title_vi: string;
  title_original: string | null;
  main_image_url: string | null;
  price_amount: string | null;
  price_currency: string | null;
  price_vnd_estimate: number | null;
  landed_estimate_vnd: number | null;
  rating: string | null;
  review_count: number | null;
  sales_count: number | null;
  ai_score: number | null;
  rank_reason: string | null;
  offers_count: number;
  guidance: RankGuidance | null;
  assessment_status: string | null;
  score_total: string | null;
  created_at: string;
};

/** c5 + c6: nguyên tắc và gu của chị đã chỉnh điểm AI thế nào. */
export type RankGuidance = {
  base_score: number | null;
  delta: number;
  violates: boolean;
  notes: { kind: "principle" | "taste"; delta: number; text: string }[];
};

export type Offer = {
  platform: string;
  url: string | null;
  seller_name: string | null;
  price_amount: string | null;
  currency: string | null;
  price_vnd_estimate: number | null;
  rating: number | null;
  review_count: number | null;
};

export type CandidateDetail = CandidateCard & {
  description_vi: string | null;
  specs: Record<string, string>;
  images: string[];
  moq: number | null;
  weight_grams: number | null;
  offers: Offer[];
};

export type Trend = {
  id: string;
  platform: string;
  title: string;
  title_vi: string;
  url: string;
  image_url: string | null;
  reason: string | null;
  metrics: { mentions?: number; growth_pct?: number; rank?: number };
  score: number | null;
  detected_on: string;
  status: "new" | "watching" | "converted" | "dismissed";
  candidate_id: string | null;
  brief_id: string | null;
};

export type DemandMention = { id: string; source: string; channel: string | null; text: string; created_at: string };

export type Demand = {
  id: string;
  title: string;
  description: string | null;
  status: "open" | "searching" | "found" | "dismissed";
  ask_count: number;
  mention_count: number;
  last_asked_at: string | null;
  find_request_id: string | null;
  mentions: DemandMention[];
  brief_id: string | null;
};

export type BriefPatch = Partial<{
  title: string;
  filters: BriefFilters;
  keywords_vi: string[];
  keywords_translated: { zh?: string[]; ja?: string[]; en?: string[] };
  target_landed_cost_max_vnd: number;
  clear_landed_cost: boolean;
  is_scheduled: boolean;
  schedule_interval_days: number;
  alert_min_score: number;
  status: BriefStatus;
}>;

export const PLATFORM_LABELS: Record<string, string> = {
  "1688": "1688",
  alibaba: "Alibaba.com",
  taobao: "Taobao",
  tmall: "Tmall",
  pinduoduo: "Pinduoduo",
  rakuten: "Rakuten",
  amazon_jp: "Amazon Nhật",
  amazon: "Amazon",
  xiaohongshu: "Tiểu Hồng Thư",
  cosme: "@cosme",
  tiktok_shop_vn: "TikTok Shop",
  shopee_vn: "Shopee",
  lazada_vn: "Lazada",
  tiki: "Tiki",
  web: "Trang web",
  offline: "Ngoài đời",
  other: "Khác",
};

export const platformLabel = (p: string) => PLATFORM_LABELS[p] ?? p;

export const sourcingKeys = {
  all: ["sourcing"] as const,
  briefs: (status?: string) => ["sourcing", "briefs", status ?? "all"] as const,
  brief: (id: string) => ["sourcing", "brief", id] as const,
  briefCandidates: (id: string, version = "") => ["sourcing", "brief", id, "candidates", version] as const,
  run: (id: string) => ["sourcing", "run", id] as const,
  candidate: (id: string) => ["sourcing", "candidate", id] as const,
  trends: ["sourcing", "trends"] as const,
  demand: ["sourcing", "demand"] as const,
};

export const isRunActive = (r?: SourcingRun | null) => !!r && (r.status === "queued" || r.status === "running");

export function useBriefs(status?: BriefStatus) {
  return useQuery({
    queryKey: sourcingKeys.briefs(status),
    queryFn: () => api.get<Paginated<Brief>>(`${BASE}/briefs`, { query: { status, size: 50 } }),
  });
}

export function useBrief(id: string) {
  return useQuery({
    queryKey: sourcingKeys.brief(id),
    queryFn: () => api.get<Brief>(`${BASE}/briefs/${id}`),
    refetchInterval: (q) => (isRunActive(q.state.data?.last_run) ? 2000 : false),
  });
}

/** `version` đổi (vd id + trạng thái lượt quét mới nhất) thì tải lại danh sách. */
export function useBriefCandidates(id: string, enabled = true, version = "") {
  return useQuery({
    queryKey: sourcingKeys.briefCandidates(id, version),
    queryFn: () => api.get<Paginated<CandidateCard>>(`${BASE}/briefs/${id}/candidates`, { query: { size: 100 } }),
    enabled,
  });
}

export function useCandidate(id: string) {
  return useQuery({ queryKey: sourcingKeys.candidate(id), queryFn: () => api.get<CandidateDetail>(`${BASE}/candidates/${id}`) });
}

/** Hỏi lại một lượt tìm mỗi 1,5 giây cho tới khi xong. */
export function useRun(id: string | null) {
  return useQuery({
    queryKey: sourcingKeys.run(id ?? "none"),
    queryFn: () => api.get<SourcingRun>(`${BASE}/runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (!q.state.data || isRunActive(q.state.data) ? 1500 : false),
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: sourcingKeys.all });
}

export function useCreateBrief() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { text: string; input_mode?: "text" | "voice" }) => api.post<Brief>(`${BASE}/briefs`, body),
    onSuccess: invalidate,
  });
}

export function usePatchBrief(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BriefPatch) => api.patch<Brief>(`${BASE}/briefs/${id}`, body),
    onSuccess: (b) => {
      qc.setQueryData(sourcingKeys.brief(id), b);
      qc.invalidateQueries({ queryKey: sourcingKeys.briefs() });
    },
  });
}

export function useReinterpret(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => api.post<Brief>(`${BASE}/briefs/${id}/reinterpret`, { text }),
    onSuccess: (b) => qc.setQueryData(sourcingKeys.brief(id), b),
  });
}

export function useRunBrief(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SourcingRun>(`${BASE}/briefs/${id}/run`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sourcingKeys.all }),
  });
}

export function useImportLink() {
  return useMutation({
    mutationFn: (body: { url: string; brief_id?: string }) => api.post<SourcingRun>(`${BASE}/import-link`, body),
  });
}

export function useImageSearch() {
  return useMutation({
    mutationFn: ({ file, note }: { file: File; note?: string }) => {
      const form = new FormData();
      form.append("file", file);
      if (note?.trim()) form.append("note", note.trim());
      return api.post<SourcingRun>(`${BASE}/image-search`, form);
    },
  });
}

export function useTrends() {
  return useQuery({ queryKey: sourcingKeys.trends, queryFn: () => api.get<Paginated<Trend>>(`${BASE}/trends`, { query: { size: 30 } }) });
}

export function useRefreshTrends() {
  return useMutation({ mutationFn: () => api.post<SourcingRun>(`${BASE}/trends/refresh`) });
}

export function useTrendBrief() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.post<Brief>(`${BASE}/trends/${id}/brief`), onSuccess: invalidate });
}

export function useDismissTrend() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.post<Trend>(`${BASE}/trends/${id}/dismiss`), onSuccess: invalidate });
}

export function useDemand() {
  return useQuery({ queryKey: sourcingKeys.demand, queryFn: () => api.get<Paginated<Demand>>(`${BASE}/demand`, { query: { size: 30 } }) });
}

export function useDemandDigest() {
  return useMutation({ mutationFn: () => api.post<SourcingRun>(`${BASE}/demand/digest`) });
}

export function useDemandBrief() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.post<Brief>(`${BASE}/demand/${id}/brief`), onSuccess: invalidate });
}

export function useDismissDemand() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.post<Demand>(`${BASE}/demand/${id}/dismiss`), onSuccess: invalidate });
}
