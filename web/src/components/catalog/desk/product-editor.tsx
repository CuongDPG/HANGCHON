"use client";

import { Megaphone } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SkeletonList } from "@/components/ui/feedback";
import { Switch } from "@/components/ui/choice";
import { Input } from "@/components/ui/field";
import { InlineSelect } from "@/components/ui/inline-select";
import { Segmented } from "@/components/ui/segmented";
import { notifySuccess } from "@/components/ui/toast";
import {
  deskProductApi,
  useCategories,
  useProductMutation,
  type DeskProduct,
  type ProductPatch,
} from "@/lib/api/catalog";
import { SaveBar, Section, useServerDraft } from "./editor-parts";

/** Phần bán hàng của sản phẩm. Lời trên trang website (AI soạn) sửa ở Nội dung → Website (`page-content-editor.tsx`). */
type Draft = {
  price_vnd: string;
  compare_at_price_vnd: string;
  sale_mode: DeskProduct["sale_mode"];
  category_id: string | null;
  weight_grams: string;
  origin_country: string | null;
  brand: string;
  gtin: string;
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
    price_vnd: p.price_vnd ? String(p.price_vnd) : "",
    compare_at_price_vnd: s(p.compare_at_price_vnd),
    sale_mode: p.sale_mode,
    category_id: p.category_id,
    weight_grams: s(p.weight_grams),
    origin_country: p.origin_country,
    brand: s(p.brand),
    gtin: s(p.gtin),
    feed_enabled: p.feed_enabled,
  };
}

function toPatch(d: Draft): ProductPatch {
  const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(/[^\d]/g, "")));
  const t = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    price_vnd: n(d.price_vnd) ?? 0,
    compare_at_price_vnd: n(d.compare_at_price_vnd),
    sale_mode: d.sale_mode,
    category_id: d.category_id,
    weight_grams: n(d.weight_grams),
    origin_country: d.origin_country,
    brand: t(d.brand),
    gtin: t(d.gtin),
    feed_enabled: d.feed_enabled,
  };
}

/** Tab «Giá và cách bán» của trang sản phẩm (e3, e6, e10, g8): giá, cách bán, nhóm hàng, xuất xứ, dữ liệu nguồn cấp. */
export function CommerceForm({ p }: { p: DeskProduct }) {
  const categories = useCategories();
  const { draft, setDraft, dirty, reset } = useServerDraft(p, toDraft, toPatch);
  const save = useProductMutation(p.id, (body: ProductPatch) => deskProductApi.patch(p.id, body));

  if (!draft) return <SkeletonList rows={6} />;

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft({ ...draft, [k]: v });
  const studio = `/desk/noi-dung/san-pham/${p.id}`;

  return (
    <div className="flex max-w-3xl flex-col gap-5 pb-24">
      <Card tone="soft" className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
        <p className="min-w-0 flex-1 text-[14px]">
          <span className="font-semibold">Nội dung trang: sửa ở Nội dung → Website.</span>{" "}
          <span className="text-ink-2">Tên, lời giới thiệu, ảnh, thông số, hỏi đáp và nút đăng lên website nằm ở xưởng nội dung, cạnh bài các kênh.</span>
        </p>
        <ButtonLink href={studio} variant="secondary" size="sm" icon={<Megaphone className="size-4" aria-hidden />} className="self-start sm:self-center">
          Mở trang Website
        </ButtonLink>
      </Card>

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

      <Section title="Nguồn cấp Google và trợ lý mua sắm">
        <div className="grid grid-cols-2 gap-3">
          <Input label="Thương hiệu (nếu có)" value={draft.brand} onChange={(e) => set("brand", e.target.value)} maxLength={120} />
          <Input label="Mã vạch GTIN" inputMode="numeric" value={draft.gtin} onChange={(e) => set("gtin", e.target.value)} maxLength={20} />
        </div>
        <Input label="Khối lượng (gam)" inputMode="numeric" value={draft.weight_grams} onChange={(e) => set("weight_grams", e.target.value)} />
        <Switch label="Có trong nguồn cấp Google và trợ lý mua sắm" checked={draft.feed_enabled} onChange={(v) => set("feed_enabled", v)} />
      </Section>

      {dirty ? <SaveBar saving={save.isPending} onReset={reset} onSave={() => save.mutate(toPatch(draft), { onSuccess: () => notifySuccess("Đã lưu") })} /> : null}
    </div>
  );
}
