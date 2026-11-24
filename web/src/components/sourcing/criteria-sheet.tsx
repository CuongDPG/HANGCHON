"use client";

import { useEffect, useState } from "react";
import { Button, Checkbox, InlineSelect, Input, Sheet } from "@/components/ui";
import type { Brief, BriefPatch, Origin } from "@/lib/api/sourcing";

export type CriteriaField = "product" | "materials" | "cost" | "origins" | "rating" | "must" | "must_not" | "prefer" | "kw_zh" | "kw_ja";

const RATINGS = [
  { value: "", label: "Không đặt ngưỡng" },
  { value: "4", label: "Từ 4,0 sao" },
  { value: "4.3", label: "Từ 4,3 sao" },
  { value: "4.5", label: "Từ 4,5 sao" },
  { value: "4.7", label: "Từ 4,7 sao" },
  { value: "4.8", label: "Từ 4,8 sao" },
];

const ORIGINS: { value: Origin; label: string }[] = [
  { value: "cn", label: "Trung Quốc (1688, Taobao)" },
  { value: "jp", label: "Nhật (Rakuten, Amazon Nhật)" },
];

const list = (s: string) =>
  s
    .split(/[,;\n]/)
    .map((x) => x.trim())
    .filter(Boolean);

/** Sửa tiêu chí AI đã hiểu (a1). Mở từ một chip, mọi trường sửa ở một chỗ. */
export function CriteriaSheet({
  brief,
  open,
  focus,
  saving,
  onClose,
  onSave,
}: {
  brief: Brief;
  open: boolean;
  focus: CriteriaField | null;
  saving: boolean;
  onClose: () => void;
  onSave: (patch: BriefPatch) => void;
}) {
  const f = brief.filters;
  const [product, setProduct] = useState(f.product_type ?? "");
  const [materials, setMaterials] = useState((f.materials ?? []).join(", "));
  const [cost, setCost] = useState(brief.target_landed_cost_max_vnd ? String(brief.target_landed_cost_max_vnd / 1000) : "");
  const [origins, setOrigins] = useState<Origin[]>(f.origins ?? []);
  const [rating, setRating] = useState(f.min_rating ? String(f.min_rating) : "");
  const [must, setMust] = useState((f.must ?? []).join(", "));
  const [mustNot, setMustNot] = useState((f.must_not ?? []).join(", "));
  const [prefer, setPrefer] = useState((f.prefer ?? []).join(", "));
  const [zh, setZh] = useState((brief.keywords_translated.zh ?? []).join(", "));
  const [ja, setJa] = useState((brief.keywords_translated.ja ?? []).join(", "));

  const costK = Number(cost.replace(/\D/g, ""));

  // Sheet đã gắn sẵn (không gắn lại khi mở) → tự đưa con trỏ vào ô chị vừa bấm.
  useEffect(() => {
    if (!open || !focus) return;
    const t = window.setTimeout(() => document.querySelector<HTMLElement>(`[data-criteria="${focus}"]`)?.focus(), 60);
    return () => window.clearTimeout(t);
  }, [open, focus]);

  function save() {
    const patch: BriefPatch = {
      filters: {
        product_type: product.trim() || null,
        materials: list(materials),
        origins,
        min_rating: rating ? Number(rating) : null,
        must: list(must),
        must_not: list(mustNot),
        prefer: list(prefer),
      },
      keywords_translated: { zh: list(zh), ja: list(ja) },
      keywords_vi: product.trim() ? [product.trim()] : brief.keywords_vi,
    };
    if (costK > 0) patch.target_landed_cost_max_vnd = costK * 1000;
    else patch.clear_landed_cost = true;
    onSave(patch);
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Sửa tiêu chí"
      description="Chị sửa chỗ AI hiểu chưa đúng. Ngăn cách nhiều ý bằng dấu phẩy."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Huỷ
          </Button>
          <Button loading={saving} onClick={save}>
            Lưu tiêu chí
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Input label="Loại hàng" value={product} onChange={(e) => setProduct(e.target.value)} data-criteria="product" />
        <Input label="Chất liệu" value={materials} onChange={(e) => setMaterials(e.target.value)} data-criteria="materials" placeholder="vd. inox 304, silicon" />
        <Input
          label="Trần giá vốn về tay"
          inputMode="numeric"
          trailing="nghìn đ"
          value={cost}
          onChange={(e) => setCost(e.target.value)}
          data-criteria="cost"
          hint="Để trống nếu không giới hạn."
        />
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">Xuất xứ ưu tiên</legend>
          {ORIGINS.map((o) => (
            <Checkbox
              key={o.value}
              label={o.label}
              checked={origins.includes(o.value)}
              onChange={(e) => setOrigins((cur) => (e.target.checked ? [...cur, o.value] : cur.filter((x) => x !== o.value)))}
            />
          ))}
        </fieldset>
        <InlineSelect label="Ngưỡng đánh giá" value={rating} onChange={setRating} options={RATINGS} />
        <Input label="Bắt buộc có" value={must} onChange={(e) => setMust(e.target.value)} data-criteria="must" />
        <Input label="Không chấp nhận" value={mustNot} onChange={(e) => setMustNot(e.target.value)} data-criteria="must_not" placeholder="vd. không pin" />
        <Input label="Ưu tiên" value={prefer} onChange={(e) => setPrefer(e.target.value)} data-criteria="prefer" />
        <Input label="Từ khoá tiếng Trung" lang="zh" value={zh} onChange={(e) => setZh(e.target.value)} data-criteria="kw_zh" />
        <Input label="Từ khoá tiếng Nhật" lang="ja" value={ja} onChange={(e) => setJa(e.target.value)} data-criteria="kw_ja" />
      </div>
    </Sheet>
  );
}
