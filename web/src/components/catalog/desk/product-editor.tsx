"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, ExternalLink, EyeOff, Plus, Send, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, SectionLabel } from "@/components/ui/card";
import { Switch } from "@/components/ui/choice";
import { useConfirm } from "@/components/ui/confirm";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { InlineSelect } from "@/components/ui/inline-select";
import { PageHeader } from "@/components/ui/page-header";
import { Seal } from "@/components/ui/seal";
import { Segmented } from "@/components/ui/segmented";
import { Sheet } from "@/components/ui/overlay";
import { notifySuccess } from "@/components/ui/toast";
import { useSession } from "@/lib/api/auth";
import {
  PRODUCT_STATUS_LABELS,
  deskProductApi,
  useCategories,
  useDeskProduct,
  useProductMutation,
  type DeskProduct,
  type Faq,
  type ProductPatch,
  type Spec,
} from "@/lib/api/catalog";
import { api } from "@/lib/api/client";
import { ImageManager } from "./image-manager";
import { sellerAddressIssues } from "./seller-voice";
import { STATUS_TONE } from "./products-screen";
import { RelatedLinks } from "@/components/desk/related-links";

type Draft = {
  name: string;
  subtitle: string;
  short_description: string;
  description: string;
  reason_selected: string;
  not_satisfied: string;
  trial_days: string;
  price_vnd: string;
  compare_at_price_vnd: string;
  sale_mode: DeskProduct["sale_mode"];
  category_id: string | null;
  specs: Spec[];
  faq: Faq[];
  weight_grams: string;
  origin_country: string | null;
  brand: string;
  gtin: string;
  seo_title: string;
  seo_description: string;
  feed_enabled: boolean;
};

const ORIGINS = [
  { value: "JP", label: "Nhật" },
  { value: "CN", label: "Trung Quốc" },
  { value: "KR", label: "Hàn Quốc" },
  { value: "TW", label: "Đài Loan" },
  { value: "VN", label: "Việt Nam" },
  { value: "US", label: "Mỹ" },
];

function toDraft(p: DeskProduct): Draft {
  const s = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    name: p.name,
    subtitle: s(p.subtitle),
    short_description: s(p.short_description),
    description: s(p.description),
    reason_selected: s(p.reason_selected),
    not_satisfied: s(p.not_satisfied),
    trial_days: s(p.trial_days),
    price_vnd: p.price_vnd ? String(p.price_vnd) : "",
    compare_at_price_vnd: s(p.compare_at_price_vnd),
    sale_mode: p.sale_mode,
    category_id: p.category_id,
    specs: p.specs.map((x) => ({ label: x.label, value: x.value, source: x.source ?? null })),
    faq: p.faq.map((x) => ({ q: x.q, a: x.a, source: x.source ?? null })),
    weight_grams: s(p.weight_grams),
    origin_country: p.origin_country,
    brand: s(p.brand),
    gtin: s(p.gtin),
    seo_title: s(p.seo_title),
    seo_description: s(p.seo_description),
    feed_enabled: p.feed_enabled,
  };
}

function toPatch(d: Draft): ProductPatch {
  const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[^\d]/g, "")));
  const t = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    name: d.name.trim(),
    subtitle: t(d.subtitle),
    short_description: t(d.short_description),
    description: t(d.description),
    reason_selected: t(d.reason_selected),
    not_satisfied: t(d.not_satisfied),
    trial_days: n(d.trial_days),
    price_vnd: n(d.price_vnd) ?? 0,
    compare_at_price_vnd: n(d.compare_at_price_vnd),
    sale_mode: d.sale_mode,
    category_id: d.category_id,
    specs: d.specs.filter((x) => x.label.trim() && x.value.trim()),
    faq: d.faq.filter((x) => x.q.trim() && x.a.trim()),
    weight_grams: n(d.weight_grams),
    origin_country: d.origin_country,
    brand: t(d.brand),
    gtin: t(d.gtin),
    seo_title: t(d.seo_title),
    seo_description: t(d.seo_description),
    feed_enabled: d.feed_enabled,
  };
}

type Checks = {
  dropped_specs?: string[];
  dropped_faq?: string[];
  unsupported_numbers?: { field: string; numbers: string[] }[];
  overclaims?: string[];
  pronouns?: string[];
};

type TextKey = "name" | "subtitle" | "short_description" | "description" | "reason_selected" | "not_satisfied" | "seo_title" | "seo_description";
const VOICE_FIELDS: [TextKey, string][] = [
  ["name", "Tên"],
  ["subtitle", "Dòng phụ"],
  ["short_description", "Mô tả ngắn"],
  ["description", "Mô tả"],
  ["reason_selected", "Vì sao mình chọn"],
  ["not_satisfied", "Điều mình chưa ưng"],
  ["seo_title", "Tiêu đề tìm kiếm"],
  ["seo_description", "Mô tả tìm kiếm"],
];

type VoiceIssue = { key: string; field: string; quote: string; suggestion: string; apply: (d: Draft) => Draft };

/** Chỗ trên bản nháp còn gọi người bán là «chị» (khách đọc trang này), kèm cách sửa theo gợi ý. */
function draftVoiceIssues(d: Draft): VoiceIssue[] {
  const out: VoiceIssue[] = [];
  const swap = (text: string, q: string, s: string) => text.replace(q, s);
  for (const [k, label] of VOICE_FIELDS) {
    for (const h of sellerAddressIssues(d[k])) {
      out.push({ key: `${k}:${h.quote}`, field: label, ...h, apply: (x) => ({ ...x, [k]: swap(x[k], h.quote, h.suggestion) }) });
    }
  }
  d.specs.forEach((row, i) => {
    for (const part of ["label", "value"] as const)
      for (const h of sellerAddressIssues(row[part]))
        out.push({
          key: `spec${i}${part}:${h.quote}`, field: `Thông số ${i + 1}`, ...h,
          apply: (x) => ({ ...x, specs: x.specs.map((r, j) => (j === i ? { ...r, [part]: swap(r[part], h.quote, h.suggestion) } : r)) }),
        });
  });
  d.faq.forEach((row, i) => {
    for (const part of ["q", "a"] as const)
      for (const h of sellerAddressIssues(row[part]))
        out.push({
          key: `faq${i}${part}:${h.quote}`, field: `Hỏi đáp ${i + 1} (${part === "q" ? "câu hỏi" : "trả lời"})`, ...h,
          apply: (x) => ({ ...x, faq: x.faq.map((r, j) => (j === i ? { ...r, [part]: swap(r[part], h.quote, h.suggestion) } : r)) }),
        });
  });
  return out;
}

const FIELD_LABELS: Record<string, string> = { name: "tên", subtitle: "dòng phụ", short_description: "mô tả ngắn", description: "mô tả" };

/** Sửa trang sản phẩm (e1, e6): lời AI soạn, giá, thông số, hỏi–đáp, ảnh; rồi chị đăng. */
export function ProductEditor({ id }: { id: string }) {
  const { data: p, isPending, error } = useDeskProduct(id);
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const categories = useCategories();
  const confirm = useConfirm();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [note, setNote] = useState("");

  // dữ liệu máy chủ đổi (vừa lưu, vừa tải) → làm mới bản nháp ngay trong lúc render (không cần effect)
  const [source, setSource] = useState<DeskProduct | undefined>();
  if (p && p !== source) {
    setSource(p);
    setDraft(toDraft(p));
  }

  const checks = useQuery({
    queryKey: ["control", "approval", p?.approval_item_id],
    enabled: !!p?.approval_item_id && p.status === "pending_review",
    queryFn: () => api.get<{ status: string; preview: { checks?: Checks } }>(`/api/desk/control/approvals/${p!.approval_item_id}`),
  });

  const save = useProductMutation(id, (body: ProductPatch) => deskProductApi.patch(id, body));
  const publish = useProductMutation(id, async (body: ProductPatch | null) => {
    if (body) await deskProductApi.patch(id, body);
    return deskProductApi.publish(id);
  });
  const unpublish = useProductMutation(id, () => deskProductApi.unpublish(id));
  const rewrite = useProductMutation(id, (n: string) => deskProductApi.rewrite(id, n));

  const dirty = useMemo(() => !!(p && draft && JSON.stringify(toPatch(draft)) !== JSON.stringify(toPatch(toDraft(p)))), [p, draft]);

  if (isPending) return <SkeletonList rows={6} />;
  if (error || !p) return <EmptyState tone="error" title="Chưa tải được sản phẩm" description={error?.message} />;
  if (!draft) return <SkeletonList rows={6} />;

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft({ ...draft, [k]: v });
  const c = checks.data?.status === "pending" ? checks.data.preview.checks : undefined;
  const warnings = c
    ? [
        ...(c.dropped_specs ?? []).map((x) => `Bỏ thông số không có trong hồ sơ: ${x}`),
        ...(c.dropped_faq ?? []).map((x) => `Bỏ câu hỏi không có căn cứ: ${x}`),
        ...(c.unsupported_numbers ?? []).map((x) => `Số liệu lạ ở ${FIELD_LABELS[x.field] ?? x.field}: ${x.numbers.join(", ")}`),
        ...(c.overclaims?.length ? [`Có từ nói quá: ${c.overclaims.join(", ")}`] : []),
        // «chị» đã hiện riêng ở thẻ «Xưng hô với khách» (tính theo bản nháp đang sửa)
      ]
    : [];
  const voice = draftVoiceIssues(draft);
  const funnel = p.dossier?.funnel;

  return (
    <div className="flex flex-col gap-5 pb-24">
      <PageHeader
        title={p.name}
        eyebrow={p.candidate_title && p.candidate_title !== p.name ? `Từ ứng viên: ${p.candidate_title}` : "Sản phẩm"}
        backHref="/desk/san-pham"
        actions={<Badge tone={STATUS_TONE[p.status]}>{PRODUCT_STATUS_LABELS[p.status]}</Badge>}
      />
      <RelatedLinks
        links={[
          { href: `/desk/noi-dung/san-pham/${p.id}`, label: "Bài các kênh" },
          p.candidate_id && { href: `/desk/san-hang/ung-vien/${p.candidate_id}`, label: "Hồ sơ thẩm định" },
          p.status === "published" && { href: `/san-pham/${p.slug}`, label: "Xem trên web" },
        ]}
      />

      {voice.length ? (
        <Card tone="danger" aria-label="Xưng hô với khách">
          <p className="flex items-center gap-1.5 text-[15px] font-semibold">
            <CircleAlert className="size-4 text-seal" aria-hidden /> Trang còn gọi người bán là «chị» ở {voice.length} chỗ
          </p>
          <p className="mt-0.5 text-[13.5px] text-ink-2">Khách đọc trang này: người bán xưng «mình», gọi khách «bạn». Sửa xong mới đăng được.</p>
          <ul className="mt-2 flex flex-col gap-2">
            {voice.map((v) => (
              <li key={v.key} className="flex flex-col gap-1.5 rounded-md bg-surface px-3 py-2 sm:flex-row sm:items-center sm:gap-3">
                <div className="min-w-0 flex-1 text-[14px]">
                  <p className="text-[12.5px] font-semibold text-ink-2">{v.field}</p>
                  <p className="text-ink-2 line-through decoration-seal/60">{v.quote}</p>
                  <p>{v.suggestion}</p>
                </div>
                <Button size="sm" variant="secondary" className="self-start sm:self-center" onClick={() => setDraft(v.apply(draft))}>
                  Sửa theo gợi ý
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {warnings.length ? (
        <Card tone="danger">
          <p className="flex items-center gap-1.5 text-[15px] font-semibold">
            <CircleAlert className="size-4 text-seal" aria-hidden /> AI tự soát, chị xem kỹ {warnings.length} chỗ
          </p>
          <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[14px] text-ink-2">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {isOwner && p.status !== "published" ? (
          <Button icon={<Send className="size-4" />} loading={publish.isPending} disabled={voice.length > 0} onClick={() => publish.mutate(dirty ? toPatch(draft) : null, { onSuccess: () => notifySuccess("Đã đăng lên kệ") })}>
            {dirty ? "Lưu và đăng lên kệ" : "Đăng lên kệ"}
          </Button>
        ) : null}
        {dirty ? (
          <Button variant={p.status === "published" || !isOwner ? "primary" : "secondary"} loading={save.isPending} onClick={() => save.mutate(toPatch(draft), { onSuccess: () => notifySuccess("Đã lưu") })}>
            Lưu thay đổi
          </Button>
        ) : null}
        {p.status !== "published" && p.candidate_id ? (
          <Button variant="secondary" icon={<Sparkles className="size-4" />} onClick={() => setRewriteOpen(true)}>
            AI viết lại
          </Button>
        ) : null}
        {p.status === "published" ? (
          <>
            <ButtonLink href={`/san-pham/${p.slug}`} variant="secondary" icon={<ExternalLink className="size-4" />} target="_blank">
              Xem trên web
            </ButtonLink>
            {isOwner ? (
              <Button
                variant="ghost"
                icon={<EyeOff className="size-4" />}
                onClick={async () => {
                  if (await confirm({ title: "Tạm ẩn món này?", message: "Món sẽ không hiện trên kệ cho tới khi chị đăng lại.", confirmLabel: "Tạm ẩn" }))
                    unpublish.mutate(undefined, { onSuccess: () => notifySuccess("Đã tạm ẩn") });
                }}
              >
                Tạm ẩn
              </Button>
            ) : null}
          </>
        ) : null}
      </div>

      <Section title="Ảnh">
        <ImageManager product={p} />
      </Section>

      <Section title="Lời trên trang">
        <Input label="Tên món" value={draft.name} onChange={(e) => set("name", e.target.value)} maxLength={200} required />
        <Input label="Dòng phụ" hint="vd. Nhật Bản · inox 316 · 310 g" value={draft.subtitle} onChange={(e) => set("subtitle", e.target.value)} maxLength={300} />
        <Textarea label="Vì sao mình chọn" hint="Mỗi lý do một dòng." value={draft.reason_selected} onChange={(e) => set("reason_selected", e.target.value)} rows={3} />
        <Textarea label="Điều mình chưa ưng" value={draft.not_satisfied} onChange={(e) => set("not_satisfied", e.target.value)} rows={2} />
        <Textarea label="Mô tả ngắn" value={draft.short_description} onChange={(e) => set("short_description", e.target.value)} rows={2} />
        <Textarea label="Mô tả" hint="Đoạn cách nhau một dòng trống; dòng bắt đầu bằng «-» là gạch đầu dòng." value={draft.description} onChange={(e) => set("description", e.target.value)} rows={5} />
        <Input label="Số ngày dùng thử" type="number" inputMode="numeric" min={0} value={draft.trial_days} onChange={(e) => set("trial_days", e.target.value)} />
      </Section>

      <Section title="Giá và cách bán">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Giá bán" inputMode="numeric" trailing="đ" value={draft.price_vnd} onChange={(e) => set("price_vnd", e.target.value)} error={!draft.price_vnd ? "Cần giá trước khi đăng" : undefined} />
          <Input label="Giá gạch" hint="Không bắt buộc" inputMode="numeric" trailing="đ" value={draft.compare_at_price_vnd} onChange={(e) => set("compare_at_price_vnd", e.target.value)} />
        </div>
        <Segmented
          aria-label="Cách bán"
          block
          value={draft.sale_mode}
          onChange={(v) => set("sale_mode", v)}
          options={[
            { value: "drop", label: "Theo đợt" },
            { value: "in_stock", label: "Giữ sẵn" },
            { value: "both", label: "Cả hai" },
          ]}
        />
        <div className="grid grid-cols-2 gap-3">
          <InlineSelect
            label="Nhóm hàng"
            value={draft.category_id}
            onChange={(v) => set("category_id", v)}
            placeholder="Chọn nhóm"
            options={(categories.data ?? []).map((x) => ({ value: x.id, label: x.name }))}
          />
          <InlineSelect label="Xuất xứ" value={draft.origin_country} onChange={(v) => set("origin_country", v)} placeholder="Chọn" options={ORIGINS} />
        </div>
      </Section>

      <Section title="Thông số">
        <RowsEditor
          rows={draft.specs}
          onChange={(rows) => set("specs", rows)}
          empty={{ label: "", value: "" }}
          render={(row, update) => (
            <>
              <Input aria-label="Tên thông số" placeholder="vd. Dung tích" value={row.label} onChange={(e) => update({ ...row, label: e.target.value })} wrapperClassName="flex-1" maxLength={80} />
              <Input aria-label="Giá trị" placeholder="vd. 480 ml" value={row.value} onChange={(e) => update({ ...row, value: e.target.value })} wrapperClassName="flex-1" maxLength={200} />
            </>
          )}
          addLabel="Thêm thông số"
        />
      </Section>

      <Section title="Hỏi đáp">
        <RowsEditor
          rows={draft.faq}
          onChange={(rows) => set("faq", rows)}
          empty={{ q: "", a: "" }}
          vertical
          render={(row, update) => (
            <>
              <Input aria-label="Câu hỏi" placeholder="Câu khách hay hỏi" value={row.q} onChange={(e) => update({ ...row, q: e.target.value })} maxLength={200} />
              <Textarea aria-label="Trả lời" placeholder="Trả lời theo đúng hồ sơ" value={row.a} onChange={(e) => update({ ...row, a: e.target.value })} rows={2} />
              {row.source ? <p className="text-[12.5px] text-ink-3">Căn cứ: {row.source}</p> : null}
            </>
          )}
          addLabel="Thêm câu hỏi"
        />
      </Section>

      <Section title="Để máy tìm kiếm và AI đọc được">
        <Input label="Tiêu đề tìm kiếm" value={draft.seo_title} onChange={(e) => set("seo_title", e.target.value)} maxLength={200} />
        <Textarea label="Mô tả tìm kiếm" value={draft.seo_description} onChange={(e) => set("seo_description", e.target.value)} maxLength={400} rows={2} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Thương hiệu (nếu có)" value={draft.brand} onChange={(e) => set("brand", e.target.value)} maxLength={120} />
          <Input label="Mã vạch GTIN" inputMode="numeric" value={draft.gtin} onChange={(e) => set("gtin", e.target.value)} maxLength={20} />
        </div>
        <Input label="Khối lượng (gam)" inputMode="numeric" value={draft.weight_grams} onChange={(e) => set("weight_grams", e.target.value)} />
        <Switch label="Có trong nguồn cấp Google và trợ lý mua sắm" checked={draft.feed_enabled} onChange={(v) => set("feed_enabled", v)} />
      </Section>

      <Section title="Hồ sơ chọn (tự lấy từ Bàn chọn)">
        <div className="flex items-center gap-3">
          {p.considered_count ? <Seal chosen={p.selected_count} total={p.considered_count} size={52} /> : null}
          <p className="text-[14px] text-ink-2">
            {funnel ? `Xem ${funnel.viewed ?? "?"} · so kỹ ${funnel.compared ?? 0} · mua thử ${funnel.tried ?? 0} · chọn ${funnel.selected ?? 1}` : "Chưa có số liệu sàng lọc."}
          </p>
        </div>
        {p.rejected_alternatives.length ? (
          <ul className="flex flex-col gap-1.5 text-[14px]">
            {p.rejected_alternatives.map((a) => (
              <li key={a.label}>
                <span className="font-semibold">{a.label}</span>
                {a.origin ? ` · ${a.origin}` : ""} — {a.reason ?? "không ghi lý do"}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="text-[12.5px] text-ink-3">Món bị loại hiện không kèm tên thương hiệu hay tên shop.</p>
      </Section>

      {dirty ? (
        // dính trên nút nổi «Nói với AI» (như thanh quyết định ở hồ sơ thẩm định) để nút nổi không che «Lưu»
        <div className="sticky bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+72px)] z-10 md:bottom-24">
          <div className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface p-2 pl-3 shadow-pop">
            <span className="text-[14px] text-ink-2">Có thay đổi chưa lưu</span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setDraft(toDraft(p))}>
                Bỏ
              </Button>
              <Button loading={save.isPending} onClick={() => save.mutate(toPatch(draft), { onSuccess: () => notifySuccess("Đã lưu") })}>
                Lưu
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <Sheet
        open={rewriteOpen}
        onClose={() => setRewriteOpen(false)}
        title="AI viết lại trang"
        description="AI chỉ dùng dữ liệu trong hồ sơ thẩm định và ghi chú thử hàng. Phần chị đã sửa sẽ bị thay."
        footer={
          <Button
            block
            loading={rewrite.isPending}
            onClick={() =>
              rewrite.mutate(note, {
                onSuccess: () => {
                  setRewriteOpen(false);
                  setNote("");
                  notifySuccess("AI đã viết lại, chị xem nhé.");
                },
              })
            }
          >
            Viết lại
          </Button>
        }
      >
        <Textarea label="Dặn AI (không bắt buộc)" placeholder="vd. viết ngắn hơn, nói rõ miệng bình hẹp" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
      </Sheet>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <SectionLabel>{title}</SectionLabel>
      {children}
    </section>
  );
}

function RowsEditor<T extends object>({
  rows,
  onChange,
  render,
  empty,
  addLabel,
  vertical = false,
}: {
  rows: T[];
  onChange: (rows: T[]) => void;
  render: (row: T, update: (row: T) => void) => React.ReactNode;
  empty: T;
  addLabel: string;
  vertical?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, i) => (
        <div key={i} className={vertical ? "flex flex-col gap-2 rounded-md border border-line p-3" : "flex items-start gap-2"}>
          {render(row, (r) => onChange(rows.map((x, j) => (j === i ? r : x))))}
          <IconButton label="Xoá dòng" icon={<Trash2 />} className={vertical ? "self-end" : undefined} onClick={() => onChange(rows.filter((_, j) => j !== i))} />
        </div>
      ))}
      <Button variant="ghost" size="sm" icon={<Plus className="size-4" />} onClick={() => onChange([...rows, { ...empty }])} className="self-start">
        {addLabel}
      </Button>
    </div>
  );
}
