/**
 * API của module catalog (website + desk/san-pham). Hàm `catalogApi.*` chạy được ở Server và Client Component;
 * hook `use*` (TanStack Query) chỉ dùng trong Client Component của bàn làm việc.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

/* ---------------- kiểu dữ liệu công khai ---------------- */

export type ImageSet = {
  id: string;
  alt: string | null;
  is_primary: boolean;
  status: string;
  src: string | null;
  src_large: string | null;
  src_small: string | null;
  webp: Record<string, string>;
};

export type SealInfo = { chosen: number; total: number | null };
export type DropRef = {
  id: string;
  slug: string;
  label: string;
  title: string;
  closes_at: string | null;
  expected_arrival_date: string | null;
  price_vnd: number;
  slots_total: number | null;
  slots_left: number | null;
  max_per_order: number | null;
};

export type ProductCard = {
  id: string;
  slug: string;
  name: string;
  subtitle: string | null;
  price_vnd: number;
  list_price_vnd: number;
  compare_at_price_vnd: number | null;
  image: ImageSet | null;
  seal: SealInfo;
  trial_days: number | null;
  origin: string | null;
  proof: string | null;
  category: { slug: string; name: string } | null;
  rating_avg: number | null;
  review_count: number;
  drop: DropRef | null;
  stock: number;
  available: boolean;
};

export type Shelf = {
  total: number;
  chips: { slug: string; name: string; count: number }[];
  items: ProductCard[];
  query: string | null;
  category: string | null;
};

export type Funnel = { viewed?: number | null; compared?: number | null; tried?: number | null; selected?: number | null };
export type Spec = { label: string; value: string; source?: string | null };
export type Faq = { q: string; a: string; source?: string | null };
export type PublicReview = {
  id: string;
  display_name: string;
  rating: number | null;
  body: string | null;
  photos: { src: string | null; thumb: string | null }[];
  published_at: string | null;
  owner_reply: string | null;
};

export type ProductDetail = ProductCard & {
  short_description: string | null;
  description: string | null;
  specs: Spec[];
  faq: Faq[];
  reason_selected: string[];
  not_satisfied: string | null;
  images: ImageSet[];
  funnel: Funnel;
  weight_grams: number | null;
  brand: string | null;
  gtin: string | null;
  shipping_notes: string[];
  sale_mode: string;
  seo_title: string | null;
  seo_description: string | null;
  published_at: string | null;
  updated_at: string;
  ai_generated: boolean;
  reviews: PublicReview[];
  url: string;
  /** Tên người chọn (Cài đặt `store.picker_name`); chưa đặt thì là tên trung tính mặc định. */
  picker_name?: string | null;
};

export type Alternative = {
  label: string;
  origin: string | null;
  price_vnd: number | null;
  summary: string | null;
  reason: string | null;
  tags: string[];
  stage: "tried" | "compared" | string;
};

export type Dossier = {
  product: {
    slug: string;
    name: string;
    price_vnd: number;
    origin: string | null;
    summary: string;
    image: ImageSet | null;
    seal: SealInfo;
    trial_days: number | null;
    reason_selected: string[];
    not_satisfied: string | null;
  };
  funnel: Funnel;
  alternatives: Alternative[];
  reject_groups: { key: string; label: string; count: number }[];
  screened_out: number;
  reviews_read: number;
  review_languages: string[];
  picker_name: string | null;
};

export type DropSummary = {
  id: string;
  slug: string;
  code: string;
  label: string;
  title: string;
  description: string | null;
  status: string;
  opens_at: string | null;
  closes_at: string | null;
  expected_arrival_date: string | null;
  actual_arrival_date: string | null;
  item_count: number;
  slots_total: number | null;
  slots_reserved: number;
  cover: ImageSet | null;
  product_names: string[];
  order_count: number;
  rating_avg: number | null;
  review_count: number;
};

export type DropDetail = DropSummary & {
  deposit_pct: number | null;
  items: (ProductCard & { slots_total: number | null; slots_left: number | null; max_per_order: number | null })[];
};

export type DropsOverview = { open: DropSummary[]; upcoming: DropSummary[]; arrived: DropSummary[]; closed: DropSummary[] };

export type About = {
  store_name: string;
  tagline: string;
  picker_name: string;
  intro: string;
  not_selling: string;
  not_selling_rules: string[];
  ai_help: string;
  how_we_choose: string[];
  stats: { viewed: number; chosen: number; published: number; ratio_pct: number | null };
};

export type FindStatusKey = "new" | "threshold" | "searching" | "trying" | "found" | "none" | "pending" | "rejected";
export type FindRequestPublic = {
  slug: string;
  title: string;
  description: string | null;
  budget_vnd: number | null;
  vote_count: number;
  vote_threshold: number;
  status: { key: FindStatusKey | (string & {}); label: string };
  voted: boolean;
  product_slug: string | null;
  created_at: string;
};
export type FindRequestsPage = { items: FindRequestPublic[]; total: number; threshold: number };
export type FindRequestInput = {
  title: string;
  description?: string;
  budget_vnd?: number | null;
  contact_name?: string;
  contact?: string;
  website?: string;
};

export type ReviewInvite = {
  status: "requested" | "submitted" | "pending_review" | "published" | "rejected" | "hidden" | "expired";
  product_name: string;
  product_slug: string;
  product_image: ImageSet | null;
  display_name: string | null;
  rating: number | null;
  body: string | null;
};

export type SitemapEntry = { path: string; lastmod: string | null; priority: number };

/* ---------------- gọi API công khai ---------------- */

export const catalogApi = {
  shelf: (query: { q?: string | null; nhom?: string | null } = {}) => api.get<Shelf>("/api/store/catalog/shelf", { query }),
  product: (slug: string) => api.get<ProductDetail>(`/api/store/catalog/products/${encodeURIComponent(slug)}`),
  dossier: (slug: string) => api.get<Dossier>(`/api/store/catalog/products/${encodeURIComponent(slug)}/dossier`),
  drops: () => api.get<DropsOverview>("/api/store/catalog/drops"),
  drop: (slug: string) => api.get<DropDetail>(`/api/store/catalog/drops/${encodeURIComponent(slug)}`),
  remind: (slug: string, contact: string) =>
    api.post<{ added: boolean }>(`/api/store/catalog/drops/${encodeURIComponent(slug)}/remind`, { contact }),
  about: () => api.get<About>("/api/store/catalog/about"),
  finds: () => api.get<FindRequestsPage>("/api/store/catalog/finds"),
  createFind: (input: FindRequestInput) =>
    api.post<{ request: FindRequestPublic; duplicate: boolean; visible: boolean }>("/api/store/catalog/finds", input),
  vote: (slug: string) =>
    api.post<{ request: FindRequestPublic; added: boolean }>(`/api/store/catalog/finds/${encodeURIComponent(slug)}/vote`, {}),
  reviewInvite: (token: string) => api.get<ReviewInvite>(`/api/store/catalog/reviews/${encodeURIComponent(token)}`),
  submitReview: (token: string, form: FormData) =>
    api.post<ReviewInvite>(`/api/store/catalog/reviews/${encodeURIComponent(token)}`, form),
  sitemap: () => api.get<SitemapEntry[]>("/api/store/catalog/sitemap"),
};

/* ---------------- desk ---------------- */

export type ProductStatus = "draft" | "pending_review" | "published" | "paused" | "archived";
export type DeskProductRow = {
  id: string;
  slug: string;
  name: string;
  status: ProductStatus;
  price_vnd: number;
  selected_count: number;
  considered_count: number | null;
  image: ImageSet | null;
  approval_item_id: string | null;
  ai_generated: boolean;
  review_count: number;
  rating_avg: number | null;
  updated_at: string;
};

export type DeskProduct = {
  id: string;
  candidate_id: string | null;
  candidate_title: string | null;
  category_id: string | null;
  slug: string;
  name: string;
  subtitle: string | null;
  short_description: string | null;
  description: string | null;
  specs: Spec[];
  faq: Faq[];
  status: ProductStatus;
  published_at: string | null;
  sale_mode: "drop" | "in_stock" | "both";
  price_vnd: number;
  compare_at_price_vnd: number | null;
  selected_count: number;
  considered_count: number | null;
  trial_days: number | null;
  reason_selected: string | null;
  not_satisfied: string | null;
  rejected_alternatives: Alternative[];
  dossier: { funnel?: Funnel; reject_groups?: Dossier["reject_groups"]; screened_out?: number };
  weight_grams: number | null;
  origin_country: string | null;
  brand: string | null;
  gtin: string | null;
  seo_title: string | null;
  seo_description: string | null;
  feed_enabled: boolean;
  ai_generated: boolean;
  approval_item_id: string | null;
  rating_avg: number | null;
  review_count: number;
  images: ImageSet[];
  updated_at: string;
};

export type ProductPatch = Partial<
  Pick<
    DeskProduct,
    | "name"
    | "subtitle"
    | "short_description"
    | "description"
    | "specs"
    | "faq"
    | "price_vnd"
    | "compare_at_price_vnd"
    | "category_id"
    | "sale_mode"
    | "reason_selected"
    | "not_satisfied"
    | "trial_days"
    | "weight_grams"
    | "origin_country"
    | "brand"
    | "gtin"
    | "seo_title"
    | "seo_description"
    | "feed_enabled"
  >
>;

export type Category = { id: string; slug: string; name: string };
export type SelectableCandidate = { id: string; title_vi: string; stage_changed_at: string | null };

export type DropStatus =
  | "draft"
  | "pending_review"
  | "scheduled"
  | "open"
  | "closed"
  | "sourcing"
  | "arriving"
  | "fulfilling"
  | "completed"
  | "cancelled";

export type DeskDropItem = {
  id: string;
  product_id: string;
  price_vnd: number;
  slots_total: number | null;
  slots_reserved: number;
  max_per_order: number | null;
  position: number;
};

export type DeskDrop = {
  id: string;
  code: string;
  label: string;
  slug: string;
  title: string;
  description: string | null;
  status: DropStatus;
  opens_at: string | null;
  closes_at: string | null;
  expected_arrival_date: string | null;
  actual_arrival_date: string | null;
  deposit_pct: number | null;
  approval_item_id: string | null;
  items: DeskDropItem[];
  reminder_count: number;
  product_names: Record<string, string>;
  updated_at: string;
};

export type DropItemInput = { product_id: string; price_vnd?: number | null; slots_total?: number | null; max_per_order?: number | null };
export type DropInput = {
  title: string;
  description?: string | null;
  opens_at?: string | null;
  closes_at?: string | null;
  expected_arrival_date?: string | null;
  deposit_pct?: number | null;
  items?: DropItemInput[];
};

export type ReviewStatus = ReviewInvite["status"];
export type DeskReview = {
  id: string;
  product_id: string;
  product_name: string | null;
  status: ReviewStatus;
  display_name: string | null;
  rating: number | null;
  body: string | null;
  photo_urls: (string | null)[];
  submitted_at: string | null;
  published_at: string | null;
  ai_flags: { spam?: boolean; offensive?: boolean; personal_info?: boolean; off_topic?: boolean; recommend?: "publish" | "hide" };
  ai_summary: string | null;
  owner_reply: string | null;
};

export type FindStatus = "pending_review" | "open" | "threshold_reached" | "searching" | "found" | "closed" | "rejected";
export type DeskFindRequest = {
  id: string;
  public_slug: string;
  title: string;
  description: string | null;
  budget_vnd: number | null;
  status: FindStatus;
  contact_name: string | null;
  contact: string | null;
  vote_count: number;
  vote_threshold: number;
  brief_id: string | null;
  product_id: string | null;
  moderation_note: string | null;
  created_at: string;
  public_status: { key: string; label: string };
};

const D = "/api/desk/catalog";

export const catalogKeys = {
  all: ["catalog"] as const,
  products: (q: object) => ["catalog", "products", q] as const,
  product: (id: string) => ["catalog", "product", id] as const,
  categories: ["catalog", "categories"] as const,
  selectable: ["catalog", "selectable"] as const,
  drops: (q: object) => ["catalog", "drops", q] as const,
  drop: (id: string) => ["catalog", "drop", id] as const,
  reviews: (q: object) => ["catalog", "reviews", q] as const,
  finds: (q: object) => ["catalog", "finds", q] as const,
};

export function useDeskProducts(query: { status?: ProductStatus | null; q?: string | null; size?: number } = {}) {
  return useQuery({
    queryKey: catalogKeys.products(query),
    queryFn: () => api.get<Paginated<DeskProductRow>>(`${D}/products`, { query: { size: 100, ...query } }),
  });
}

export function useDeskProduct(id: string) {
  return useQuery({ queryKey: catalogKeys.product(id), queryFn: () => api.get<DeskProduct>(`${D}/products/${id}`) });
}

export function useCategories() {
  return useQuery({ queryKey: catalogKeys.categories, queryFn: () => api.get<Category[]>(`${D}/categories`), staleTime: 300_000 });
}

export function useSelectableCandidates() {
  return useQuery({ queryKey: catalogKeys.selectable, queryFn: () => api.get<SelectableCandidate[]>(`${D}/candidates/selectable`) });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: catalogKeys.all });
}

export function useFromCandidate() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: (candidateId: string) => api.post<DeskProduct>(`${D}/products/from-candidate`, { candidate_id: candidateId }),
    onSuccess: done,
  });
}

export function useProductMutation<V>(id: string, fn: (vars: V) => Promise<DeskProduct>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(catalogKeys.product(id), data);
      qc.invalidateQueries({ queryKey: ["catalog", "products"] });
    },
  });
}

export const deskProductApi = {
  patch: (id: string, body: ProductPatch) => api.patch<DeskProduct>(`${D}/products/${id}`, body),
  publish: (id: string) => api.post<DeskProduct>(`${D}/products/${id}/publish`),
  unpublish: (id: string) => api.post<DeskProduct>(`${D}/products/${id}/unpublish`),
  rewrite: (id: string, note?: string) => api.post<DeskProduct>(`${D}/products/${id}/rewrite`, { note: note || null }),
  upload: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<DeskProduct>(`${D}/products/${id}/images`, form);
  },
  order: (id: string, ids: string[]) => api.put<DeskProduct>(`${D}/products/${id}/images/order`, { ids }),
  primary: (id: string, imageId: string) => api.post<DeskProduct>(`${D}/products/${id}/images/${imageId}/primary`),
  removeImage: (id: string, imageId: string) => api.delete(`${D}/products/${id}/images/${imageId}`),
};

export function useDeskDrops() {
  return useQuery({
    queryKey: catalogKeys.drops({}),
    queryFn: () => api.get<Paginated<DeskDrop>>(`${D}/drops`, { query: { size: 100 } }),
  });
}

export function useDeskDrop(id: string) {
  return useQuery({ queryKey: catalogKeys.drop(id), queryFn: () => api.get<DeskDrop>(`${D}/drops/${id}`) });
}

export function useCreateDrop() {
  const done = useInvalidate();
  return useMutation({ mutationFn: (body: DropInput) => api.post<DeskDrop>(`${D}/drops`, body), onSuccess: done });
}

export function useDropMutation<V>(id: string, fn: (vars: V) => Promise<DeskDrop>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(catalogKeys.drop(id), data);
      qc.invalidateQueries({ queryKey: ["catalog", "drops"] });
    },
  });
}

export const deskDropApi = {
  patch: (id: string, body: Partial<DropInput>) => api.patch<DeskDrop>(`${D}/drops/${id}`, body),
  open: (id: string) => api.post<DeskDrop>(`${D}/drops/${id}/open`),
  close: (id: string) => api.post<DeskDrop>(`${D}/drops/${id}/close`),
  cancel: (id: string) => api.post<DeskDrop>(`${D}/drops/${id}/cancel`),
  arrived: (id: string, arrivedOn: string) => api.post<DeskDrop>(`${D}/drops/${id}/arrived`, { arrived_on: arrivedOn }),
};

export function useDeskReviews(status: ReviewStatus | null) {
  return useQuery({
    queryKey: catalogKeys.reviews({ status }),
    queryFn: () => api.get<Paginated<DeskReview>>(`${D}/reviews`, { query: { status, size: 100 } }),
  });
}

export function useReviewAction() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, note }: { id: string; action: "approve" | "reject"; note?: string }) =>
      api.post<DeskReview>(`${D}/reviews/${id}/${action}`, action === "reject" ? { note: note || null } : undefined),
    onSuccess: done,
  });
}

export function useReplyReview() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, reply }: { id: string; reply: string }) => api.patch<DeskReview>(`${D}/reviews/${id}`, { owner_reply: reply }),
    onSuccess: done,
  });
}

export function useDeskFinds(status: FindStatus | null) {
  return useQuery({
    queryKey: catalogKeys.finds({ status }),
    queryFn: () => api.get<Paginated<DeskFindRequest>>(`${D}/finds`, { query: { status, size: 100 } }),
  });
}

export function useFindAction() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, status, productId, note }: { id: string; status: FindStatus | "approve"; productId?: string | null; note?: string }) =>
      status === "approve"
        ? api.post<DeskFindRequest>(`${D}/finds/${id}/approve`)
        : api.post<DeskFindRequest>(`${D}/finds/${id}/status`, { status, product_id: productId ?? null, note: note ?? null }),
    onSuccess: done,
  });
}

/* ---------------- tiện ích hiển thị ---------------- */

export const PRODUCT_STATUS_LABELS: Record<ProductStatus, string> = {
  draft: "Nháp",
  pending_review: "Chờ chị duyệt",
  published: "Đang trên kệ",
  paused: "Tạm ẩn",
  archived: "Lưu trữ",
};

export const DROP_STATUS_LABELS: Record<DropStatus, string> = {
  draft: "Nháp",
  pending_review: "Chờ chị duyệt",
  scheduled: "Đã hẹn giờ mở",
  open: "Đang mở",
  closed: "Đã đóng",
  sourcing: "Đang đặt nguồn",
  arriving: "Hàng đang về",
  fulfilling: "Đã về",
  completed: "Xong",
  cancelled: "Đã huỷ",
};

/** Đường dẫn công khai (tuyệt đối) của website — dùng cho JSON-LD, Open Graph, sitemap. */
export function siteUrl(path = ""): string {
  const base = (process.env.SITE_URL ?? process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3010").replace(/\/$/, "");
  return `${base}${path}`;
}
