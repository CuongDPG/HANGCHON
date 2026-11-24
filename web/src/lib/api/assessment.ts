"use client";

/**
 * Thẩm định (b1–b7): hồ sơ, chấm điểm, khung chấm, bảng so sánh. Backend: /api/desk/assessment.
 * Ba nút Loại / Mua mẫu / Chọn gọi API của module selection (lát cắt khác viết):
 * `POST /api/desk/selection/candidates/{id}/stage` với `{ to, reason? }`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, type Paginated } from "./client";
import { sourcingKeys, type CandidateCard, type CandidateDetail } from "./sourcing";

const BASE = "/api/desk/assessment";

export type Level = "info" | "warning" | "danger";

export type ScoreRow = {
  id: string;
  criterion_key: string;
  criterion_label: string;
  weight: string;
  position: number;
  ai_score: string | null;
  ai_reason: string | null;
  owner_score: string | null;
  owner_note: string | null;
  effective_score: string | null;
  points: number | null;
};

export type SafetyFinding = { level: Level; text: string };

export type Assessment = {
  id: string;
  candidate_id: string;
  status: "pending" | "running" | "ready" | "failed" | "stale";
  version: number;
  summary: string | null;
  strengths: string[];
  weaknesses: string[];
  specs: Record<string, string>;
  buyer_photos: { url: string; review_id?: string }[];
  score_status: "none" | "ai_draft" | "confirmed";
  score_total: string | null;
  score_confirmed_at: string | null;
  safety_status: "unchecked" | "ok" | "warning" | "blocked";
  safety: { findings?: SafetyFinding[]; docs_needed?: string[]; declaration?: string | null; owner_note?: string; materials?: string[] };
  safety_confirmed_at: string | null;
  counterfeit_risk: "unknown" | "low" | "medium" | "high";
  fake_review_risk: "unknown" | "low" | "medium" | "high";
  risk_notes: { kind: string; level: Level; text: string }[];
  sources: { url: string; title?: string }[];
  generated_at: string | null;
  error: string | null;
  scores: ScoreRow[];
  pending_steps: string[];
};

export type Quote = { id: string; original: string; vi: string | null; rating: number };
export type DigestPoint = { point: string; count: number; quotes: Quote[] };

export type ReviewDigest = {
  id: string;
  reviews_read: number;
  rating_avg: string | null;
  rating_histogram: Record<string, number>;
  praise: DigestPoint[];
  complaints: DigestPoint[];
  low_star_summary: string | null;
  low_star_reviews: { id: string; rating: number; original: string; vi: string | null; created_on?: string | null }[];
  suspicious_ratio: string | null;
  suspicious_notes: string | null;
  created_at: string;
};

export type MarketPrice = {
  id: string;
  platform: string;
  shop_name: string | null;
  title: string;
  url: string;
  price_vnd: number;
  original_price_vnd: number | null;
  sold_count: number | null;
  match_confidence: string | null;
};

export type MarketView = {
  count: number;
  low_vnd: number;
  high_vnd: number;
  median_vnd: number;
  suggested_price_vnd: number;
  margin_pct: number | null;
  captured_at: string;
  listings: MarketPrice[];
};

export type CostView = {
  source: "cost_sheet" | "estimate";
  landed_cost_vnd: number;
  lines: { label: string; amount_vnd: number }[];
  assumptions: string[];
  note: string;
};

export type Criterion = { key: string; label: string; weight: number; description?: string | null };

export type ScoringProfile = {
  id: string;
  name: string;
  category_id: string | null;
  is_default: boolean;
  criteria: Criterion[];
  pass_score: number | null;
  updated_at?: string;
};

export type ProfilePage = {
  candidate: CandidateDetail;
  brief: { id: string; title: string; considered_count: number; selected_count: number } | null;
  assessment: Assessment | null;
  review_digest: ReviewDigest | null;
  cost: CostView | null;
  market: MarketView | null;
  warnings: { level: Level; kind: string; text: string }[];
  scoring_profile: ScoringProfile;
};

export type ComparisonCell = { value: string; raw: number | null; best?: boolean; note?: string | null };

export type Comparison = {
  id: string;
  title: string;
  brief_id: string | null;
  criteria: { key: string; label: string }[];
  conclusion: string | null;
  recommended_candidate_id: string | null;
  items: { id: string; candidate_id: string; position: number; values: Record<string, ComparisonCell>; landed_cost_vnd: number | null }[];
  candidates: CandidateCard[];
  created_at: string;
};

export type StageTarget = "rejected" | "sample" | "selected";

export const assessmentKeys = {
  all: ["assessment"] as const,
  profile: (candidateId: string) => ["assessment", "profile", candidateId] as const,
  profiles: ["assessment", "scoring-profiles"] as const,
  comparison: (id: string) => ["assessment", "comparison", id] as const,
  comparisons: (briefId?: string) => ["assessment", "comparisons", briefId ?? "all"] as const,
};

const isAssessing = (p?: ProfilePage) => !!p?.assessment && ["pending", "running"].includes(p.assessment.status);

export function useProfile(candidateId: string) {
  return useQuery({
    queryKey: assessmentKeys.profile(candidateId),
    queryFn: () => api.get<ProfilePage>(`${BASE}/candidates/${candidateId}`),
    refetchInterval: (q) => (isAssessing(q.state.data) ? 2000 : false),
  });
}

export function useRunAssessment(candidateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (steps?: string[]) => api.post<Assessment>(`${BASE}/candidates/${candidateId}/run`, steps ? { steps } : {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: assessmentKeys.profile(candidateId) }),
  });
}

function useRefreshProfile(candidateId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: assessmentKeys.profile(candidateId) });
    qc.invalidateQueries({ queryKey: sourcingKeys.all });
  };
}

export function useSetScore(candidateId: string, assessmentId: string) {
  const refresh = useRefreshProfile(candidateId);
  return useMutation({
    mutationFn: ({ key, owner_score, owner_note }: { key: string; owner_score: number | null; owner_note?: string | null }) =>
      api.patch<Assessment>(`${BASE}/assessments/${assessmentId}/scores/${key}`, { owner_score, owner_note }),
    onSuccess: refresh,
  });
}

export function useConfirmScore(candidateId: string, assessmentId: string) {
  const refresh = useRefreshProfile(candidateId);
  return useMutation({ mutationFn: () => api.post<Assessment>(`${BASE}/assessments/${assessmentId}/confirm-score`), onSuccess: refresh });
}

export function useConfirmSafety(candidateId: string, assessmentId: string) {
  const refresh = useRefreshProfile(candidateId);
  return useMutation({
    mutationFn: (body: { status?: "ok" | "warning" | "blocked"; note?: string }) =>
      api.post<Assessment>(`${BASE}/assessments/${assessmentId}/confirm-safety`, body),
    onSuccess: refresh,
  });
}

/** Ba nút Loại / Mua mẫu / Chọn → API của module Bàn chọn. Lỗi 404/405 = API đó chưa có ở máy chủ này. */
export function useChangeStage(candidateId: string) {
  const refresh = useRefreshProfile(candidateId);
  return useMutation({
    meta: { silentError: true },
    mutationFn: async (body: { to: StageTarget; reason?: string }) => {
      try {
        return await api.post<unknown>(`/api/desk/selection/candidates/${candidateId}/stage`, body);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 404 || err.status === 405) && !(typeof err.detail === "string" && err.detail.includes("ứng viên"))) {
          throw new ApiError("Bàn chọn chưa sẵn sàng trên máy chủ này, chị thử lại sau.", err.status, err.detail);
        }
        throw err;
      }
    },
    onSuccess: refresh,
  });
}

export function useScoringProfiles() {
  return useQuery({ queryKey: assessmentKeys.profiles, queryFn: () => api.get<ScoringProfile[]>(`${BASE}/scoring-profiles`) });
}

export function usePatchProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; criteria?: Criterion[]; pass_score?: number | null }) =>
      api.patch<ScoringProfile>(`${BASE}/scoring-profiles/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: assessmentKeys.profiles }),
  });
}

export function useCreateComparison() {
  return useMutation({
    mutationFn: (candidate_ids: string[]) => api.post<Comparison>(`${BASE}/comparisons`, { candidate_ids }),
  });
}

export function useComparison(id: string) {
  return useQuery({ queryKey: assessmentKeys.comparison(id), queryFn: () => api.get<Comparison>(`${BASE}/comparisons/${id}`) });
}

export function useComparisons(briefId: string) {
  return useQuery({
    queryKey: assessmentKeys.comparisons(briefId),
    queryFn: () => api.get<Paginated<Comparison>>(`${BASE}/comparisons`, { query: { brief_id: briefId, size: 5 } }),
  });
}
