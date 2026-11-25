"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, ExternalLink, EyeOff, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useConfirm } from "@/components/ui/confirm";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/field";
import { Sheet } from "@/components/ui/overlay";
import { notifySuccess } from "@/components/ui/toast";
import { useSession } from "@/lib/api/auth";
import {
  PRODUCT_STATUS_LABELS,
  deskProductApi,
  useDeskProduct,
  useProductMutation,
  type DeskProduct,
  type Faq,
  type ProductPatch,
  type Spec,
} from "@/lib/api/catalog";
import { api } from "@/lib/api/client";
import { RowsEditor, SaveBar, Section, useServerDraft } from "./editor-parts";
import { ImageManager } from "./image-manager";
import { STATUS_TONE } from "./products-screen";
import { sellerAddressIssues } from "./seller-voice";

/** Lời trên trang website (AI soạn, chị sửa) — phần còn lại của sản phẩm (giá, cách bán, tồn kho) ở `product-editor.tsx`. */
type PageDraft = {
  name: string;
  subtitle: string;
  short_description: string;
  description: string;
  reason_selected: string;
  not_satisfied: string;
  trial_days: string;
  specs: Spec[];
  faq: Faq[];
  seo_title: string;
  seo_description: string;
};

function toDraft(p: DeskProduct): PageDraft {
  const s = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return {
    name: p.name,
    subtitle: s(p.subtitle),
    short_description: s(p.short_description),
    description: s(p.description),
    reason_selected: s(p.reason_selected),
    not_satisfied: s(p.not_satisfied),
    trial_days: s(p.trial_days),
    specs: p.specs.map((x) => ({ label: x.label, value: x.value, source: x.source ?? null })),
    faq: p.faq.map((x) => ({ q: x.q, a: x.a, source: x.source ?? null })),
    seo_title: s(p.seo_title),
    seo_description: s(p.seo_description),
  };
}

function toPatch(d: PageDraft): ProductPatch {
  const t = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    name: d.name.trim(),
    subtitle: t(d.subtitle),
    short_description: t(d.short_description),
    description: t(d.description),
    reason_selected: t(d.reason_selected),
    not_satisfied: t(d.not_satisfied),
    trial_days: d.trial_days.trim() === "" ? null : Number(d.trial_days.replace(/[^\d]/g, "")),
    specs: d.specs.filter((x) => x.label.trim() && x.value.trim()),
    faq: d.faq.filter((x) => x.q.trim() && x.a.trim()),
    seo_title: t(d.seo_title),
    seo_description: t(d.seo_description),
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

type VoiceIssue = { key: string; field: string; quote: string; suggestion: string; apply: (d: PageDraft) => PageDraft };

/** Chỗ trên bản nháp còn gọi người bán là «chị» (khách đọc trang này), kèm cách sửa theo gợi ý. */
function draftVoiceIssues(d: PageDraft): VoiceIssue[] {
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

/**
 * Kênh Website (e1, e6) trong xưởng nội dung: lời AI soạn cho trang sản phẩm, ảnh, thông số, hỏi–đáp, tìm kiếm;
 * AI viết lại; chị đăng lên website. Giá và cách bán sửa ở mục Sản phẩm — thiếu giá thì nút đăng chỉ sang đó.
 */
export function PageContentEditor({ productId }: { productId: string }) {
  const { data: p, isPending, error } = useDeskProduct(productId);
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const confirm = useConfirm();
  const qc = useQueryClient();
  const { draft, setDraft, dirty, reset } = useServerDraft(p, toDraft, toPatch);
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const [note, setNote] = useState("");

  const checks = useQuery({
    queryKey: ["control", "approval", p?.approval_item_id],
    enabled: !!p?.approval_item_id && p.status === "pending_review",
    queryFn: () => api.get<{ status: string; preview: { checks?: Checks } }>(`/api/desk/control/approvals/${p!.approval_item_id}`),
  });

  // trang đổi trạng thái → xưởng nội dung (danh sách, bài các kênh) đọc lại
  const refreshContent = () => qc.invalidateQueries({ queryKey: ["content"] });
  const save = useProductMutation(productId, (body: ProductPatch) => deskProductApi.patch(productId, body));
  const publish = useProductMutation(productId, async (body: ProductPatch | null) => {
    if (body) await deskProductApi.patch(productId, body);
    return deskProductApi.publish(productId);
  });
  const unpublish = useProductMutation(productId, () => deskProductApi.unpublish(productId));
  const rewrite = useProductMutation(productId, (n: string) => deskProductApi.rewrite(productId, n));

  if (isPending) return <SkeletonList rows={6} />;
  if (error || !p) return <EmptyState tone="error" title="Chưa tải được trang sản phẩm" description={error?.message} />;
  if (!draft) return <SkeletonList rows={6} />;

  const set = <K extends keyof PageDraft>(k: K, v: PageDraft[K]) => setDraft({ ...draft, [k]: v });
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
  const live = p.status === "published";
  const noPrice = p.price_vnd <= 0;
  const saveNow = () => save.mutate(toPatch(draft), { onSuccess: () => notifySuccess("Đã lưu") });

  return (
    <div className="flex flex-col gap-5">
      <Card className="flex flex-col gap-3">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-semibold">Trang sản phẩm trên website</p>
            <p className="text-[13px] text-ink-2">Kênh chính thức: khách bấm từ mọi bài đều về trang này.</p>
          </div>
          <Badge tone={STATUS_TONE[p.status]}>{PRODUCT_STATUS_LABELS[p.status]}</Badge>
        </div>
        {!live && noPrice ? (
          <p className="flex items-start gap-1.5 rounded-md bg-review-wash px-3 py-2 text-[14px]">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-review" aria-hidden />
            <span>
              Chưa đăng được: món chưa có giá bán (giá chị duyệt ở Nguồn cung sẽ tự điền).{" "}
              <Link href={`/desk/san-pham/${p.id}`} className="font-semibold text-accent">
                Đặt giá ở Sản phẩm →
              </Link>
            </span>
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {isOwner && !live ? (
            <Button
              icon={<Send className="size-4" />}
              loading={publish.isPending}
              disabled={voice.length > 0 || noPrice}
              onClick={() =>
                publish.mutate(dirty ? toPatch(draft) : null, {
                  onSuccess: () => {
                    void refreshContent();
                    notifySuccess("Đã đăng lên website. AI soạn bài các kênh từ trang này.");
                  },
                })
              }
            >
              {dirty ? "Lưu và đăng lên website" : "Đăng lên website"}
            </Button>
          ) : null}
          {dirty ? (
            <Button variant={live || !isOwner ? "primary" : "secondary"} loading={save.isPending} onClick={saveNow}>
              Lưu thay đổi
            </Button>
          ) : null}
          {!live && p.candidate_id ? (
            <Button variant="secondary" icon={<Sparkles className="size-4" />} onClick={() => setRewriteOpen(true)}>
              AI viết lại
            </Button>
          ) : null}
          {live ? (
            <>
              <ButtonLink href={`/san-pham/${p.slug}`} variant="secondary" icon={<ExternalLink className="size-4" />} target="_blank">
                Xem trên website
              </ButtonLink>
              {isOwner ? (
                <Button
                  variant="ghost"
                  icon={<EyeOff className="size-4" />}
                  onClick={async () => {
                    if (await confirm({ title: "Tạm ẩn trang này?", message: "Món sẽ không hiện trên website cho tới khi chị đăng lại.", confirmLabel: "Tạm ẩn" }))
                      unpublish.mutate(undefined, { onSuccess: () => { void refreshContent(); notifySuccess("Đã tạm ẩn"); } });
                  }}
                >
                  Tạm ẩn
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
        {!isOwner && !live ? <p className="text-[13px] text-ink-2">Chị là người đăng trang.</p> : null}
      </Card>

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
        <p className="text-[13px] text-ink-2">
          Thương hiệu, mã vạch, khối lượng và nguồn cấp Google sửa ở{" "}
          <Link href={`/desk/san-pham/${p.id}`} className="font-semibold text-accent">
            Sản phẩm
          </Link>
          .
        </p>
      </Section>

      {dirty ? <SaveBar saving={save.isPending} onReset={reset} onSave={saveNow} /> : null}

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
