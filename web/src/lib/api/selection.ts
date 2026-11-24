"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** Bàn chọn (c1–c6) — khớp `/api/desk/selection/**`. */

export type Stage = "candidate" | "sample" | "trial" | "selected" | "rejected";
export type PointKind = "good" | "bad" | "measure";
export type DraftStatus = "none" | "drafting" | "pending_review" | "approved";

export const STAGES: Stage[] = ["candidate", "sample", "trial", "selected", "rejected"];
export const STAGE_LABELS: Record<Stage, string> = {
  candidate: "Ứng viên",
  sample: "Mua mẫu",
  trial: "Đang thử",
  selected: "Đã chọn",
  rejected: "Đã loại",
};
export const POINT_LABELS: Record<PointKind, string> = { good: "Điểm tốt", bad: "Chưa ưng", measure: "Số đo" };

export type BoardCard = {
  id: string;
  title: string;
  image_url: string | null;
  source_platform: string;
  price_vnd_estimate: number | null;
  ai_score: number | null;
  stage: Stage;
  stage_changed_at: string | null;
  board_position: number;
  brief_id: string | null;
  category_id: string | null;
  trial_day: number | null;
  trial_days: number;
  note_count: number;
  last_note: string | null;
  last_note_at: string | null;
  landed_cost_vnd: number | null;
  seal: { chosen: number; total: number } | null;
  decision_id: string | null;
  decision_summary: string | null;
  draft_status: DraftStatus | null;
};

export type Board = { trial_days: number; counts: Record<Stage, number>; columns: Record<Stage, BoardCard[]> };

export type NotePoint = { kind: PointKind; text: string };

export type TrialNote = {
  id: string;
  candidate_id: string | null;
  kind: "voice" | "text" | "photo" | "video";
  text: string | null;
  recorded_at: string;
  trial_day: number | null;
  processing_status: "pending" | "processing" | "done" | "failed";
  ai_assigned: boolean;
  points: NotePoint[];
  photo_urls: string[];
  audio_url: string | null;
};

export type Decision = {
  id: string;
  candidate_id: string;
  decision: "selected" | "rejected";
  decided_at: string;
  trial_days: number | null;
  draft_status: DraftStatus;
  approval_item_id: string | null;
  reasons_list: string[];
  not_satisfied_list: string[];
  draft_reasons_list: string[];
  draft_not_satisfied_list: string[];
  rejection_reason: string | null;
  rejection_tags: string[];
  rejection_groups: { key: string; label: string }[];
  show_on_profile: boolean;
};

export type CandidateDetail = {
  card: BoardCard;
  title_original: string | null;
  source_url: string | null;
  description_vi: string | null;
  seller_name: string | null;
  supplier_id: string | null;
  price_amount: string | null;
  price_currency: string | null;
  weight_grams: number | null;
  rank_reason: string | null;
  notes: TrialNote[];
  decision: Decision | null;
  history: Decision[];
};

export type StageChange = { to: Stage; reason?: string; reason_tags?: string[]; position?: number };
export type StageChangeResult = { card: BoardCard; decision: Decision | null };

export type RejectReasons = { groups: { key: string; label: string }[]; frequent: { text: string; group: string; count: number }[] };
export type RejectionStats = { total: number; groups: { key: string; label: string; count: number }[]; summary: string };

export type PrincipleKind = "must" | "must_not" | "prefer" | "avoid";
export const PRINCIPLE_LABELS: Record<PrincipleKind, string> = {
  must: "Phải có",
  must_not: "Không chọn",
  prefer: "Ưu tiên",
  avoid: "Nên tránh",
};
export type Principle = {
  id: string;
  category_id: string | null;
  kind: PrincipleKind;
  text: string;
  priority: number;
  is_active: boolean;
  source: "owner" | "ai_suggested";
};
export type PrincipleInput = { kind: PrincipleKind; text: string; category_id: string | null; is_active?: boolean };

export type Category = { id: string; name: string; slug: string };

export type Trait = { trait: string; weight: number };
export type TasteProfile = {
  id: string;
  category_id: string | null;
  category_name: string | null;
  summary: string | null;
  likes: Trait[];
  dislikes: Trait[];
  sample_count: number;
  version: number;
  trained_at: string | null;
  pending_count: number;
  owner_edited: boolean;
};

const B = "/api/desk/selection";

export const selectionKeys = {
  all: ["selection"] as const,
  board: (q?: string) => ["selection", "board", q ?? ""] as const,
  candidate: (id: string) => ["selection", "candidate", id] as const,
  reasons: ["selection", "reject-reasons"] as const,
  stats: (briefId?: string | null) => ["selection", "rejection-stats", briefId ?? ""] as const,
  principles: ["selection", "principles"] as const,
  categories: ["selection", "categories"] as const,
  taste: ["selection", "taste"] as const,
  settings: ["selection", "settings"] as const,
  unassigned: ["selection", "unassigned"] as const,
};

function useInvalidateSelection() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: selectionKeys.all });
}

export function useBoard(q?: string) {
  return useQuery({ queryKey: selectionKeys.board(q), queryFn: () => api.get<Board>(`${B}/board`, { query: { q: q || undefined } }) });
}

export function useCandidate(id: string) {
  return useQuery({ queryKey: selectionKeys.candidate(id), queryFn: () => api.get<CandidateDetail>(`${B}/candidates/${id}`) });
}

export function useMoveStage() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, ...body }: StageChange & { id: string }) => api.post<StageChangeResult>(`${B}/candidates/${id}/stage`, body),
    onSettled: invalidate,
  });
}

export type NoteInput = { text?: string; voice?: boolean; photos?: File[]; audio?: File | null; durationSeconds?: number };

function noteForm(input: NoteInput): FormData {
  const fd = new FormData();
  if (input.text) fd.append("text", input.text);
  if (input.voice) fd.append("voice", "true");
  if (input.durationSeconds) fd.append("duration_seconds", String(Math.round(input.durationSeconds)));
  for (const p of input.photos ?? []) fd.append("photos", p);
  if (input.audio) fd.append("audio", input.audio);
  return fd;
}

export function useCreateNote(candidateId: string | null) {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: (input: NoteInput) =>
      api.post<TrialNote>(candidateId ? `${B}/candidates/${candidateId}/notes` : `${B}/notes`, noteForm(input)),
    onSuccess: invalidate,
  });
}

export function useUpdateNote() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; text?: string; candidate_id?: string; points?: NotePoint[] }) =>
      api.patch<TrialNote>(`${B}/notes/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useDeleteNote() {
  const invalidate = useInvalidateSelection();
  return useMutation({ mutationFn: (id: string) => api.delete(`${B}/notes/${id}`), onSuccess: invalidate });
}

export function useUnassignedNotes() {
  return useQuery({ queryKey: selectionKeys.unassigned, queryFn: () => api.get<TrialNote[]>(`${B}/notes/unassigned`) });
}

export function useApproveReasons() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; reason_selected: string[]; not_satisfied: string[] }) =>
      api.post<Decision>(`${B}/decisions/${id}/approve`, body),
    onSuccess: invalidate,
  });
}

export function useRedraftReasons() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => api.post<Decision>(`${B}/decisions/${id}/redraft`, { note }),
    onSuccess: invalidate,
  });
}

export function useUpdateRejection() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; rejection_reason?: string; rejection_tags?: string[]; show_on_profile?: boolean }) =>
      api.patch<Decision>(`${B}/decisions/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useRejectReasons() {
  return useQuery({ queryKey: selectionKeys.reasons, queryFn: () => api.get<RejectReasons>(`${B}/reject-reasons`), staleTime: 60_000 });
}

export function useRejectionStats(briefId?: string | null) {
  return useQuery({
    queryKey: selectionKeys.stats(briefId),
    queryFn: () => api.get<RejectionStats>(`${B}/rejection-stats`, { query: { brief_id: briefId ?? undefined } }),
  });
}

export function usePrinciples() {
  return useQuery({ queryKey: selectionKeys.principles, queryFn: () => api.get<Principle[]>(`${B}/principles`) });
}

export function useCategories() {
  return useQuery({ queryKey: selectionKeys.categories, queryFn: () => api.get<Category[]>(`${B}/categories`), staleTime: 5 * 60_000 });
}

export function useSavePrinciple() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, ...body }: PrincipleInput & { id?: string }) =>
      id
        ? api.patch<Principle>(`${B}/principles/${id}`, { ...body, clear_category: body.category_id === null })
        : api.post<Principle>(`${B}/principles`, body),
    onSuccess: invalidate,
  });
}

export function useTogglePrinciple() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) => api.patch<Principle>(`${B}/principles/${id}`, { is_active }),
    onSuccess: invalidate,
  });
}

export function useDeletePrinciple() {
  const invalidate = useInvalidateSelection();
  return useMutation({ mutationFn: (id: string) => api.delete(`${B}/principles/${id}`), onSuccess: invalidate });
}

export function useTasteProfiles() {
  return useQuery({ queryKey: selectionKeys.taste, queryFn: () => api.get<TasteProfile[]>(`${B}/taste-profiles`) });
}

export function useUpdateTaste() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; summary?: string; likes?: Trait[]; dislikes?: Trait[] }) =>
      api.patch<TasteProfile>(`${B}/taste-profiles/${id}`, body),
    onSuccess: invalidate,
  });
}

export function useRetrainTaste() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: () => api.post<TasteProfile[]>(`${B}/taste-profiles/retrain`, { all: true }),
    onSuccess: invalidate,
  });
}

export function useSelectionSettings() {
  return useQuery({ queryKey: selectionKeys.settings, queryFn: () => api.get<{ trial_days: number }>(`${B}/settings`) });
}

export function useUpdateSelectionSettings() {
  const invalidate = useInvalidateSelection();
  return useMutation({
    mutationFn: (body: { trial_days: number }) => api.patch<{ trial_days: number }>(`${B}/settings`, body),
    onSuccess: invalidate,
  });
}

/** Nhãn nguồn hàng ngắn gọn cho thẻ. */
export const PLATFORM_LABELS: Record<string, string> = {
  "1688": "1688",
  taobao: "Taobao",
  tmall: "Tmall",
  pinduoduo: "Pinduoduo",
  rakuten: "Rakuten",
  amazon_jp: "Amazon Nhật",
  amazon: "Amazon",
  xiaohongshu: "Tiểu Hồng Thư",
  shopee_vn: "Shopee",
  tiktok_shop_vn: "TikTok Shop",
  web: "Web",
  offline: "Ngoài đời",
};
