"use client";

import { Pencil } from "lucide-react";
import { Chip, ChipRow } from "@/components/ui";
import type { Brief } from "@/lib/api/sourcing";
import { formatVndCompact } from "@/lib/format";
import type { CriteriaField } from "./criteria-sheet";

const ORIGIN_LABEL: Record<string, string> = { cn: "Trung Quốc", jp: "Nhật", kr: "Hàn" };

/** «AI HIỂU LÀ»: mỗi tiêu chí một chip, bấm để sửa. */
export function CriteriaChips({ brief, onEdit }: { brief: Brief; onEdit: (field: CriteriaField) => void }) {
  const f = brief.filters;
  const chips: { key: string; field: CriteriaField; label: string }[] = [];
  if (f.product_type) chips.push({ key: "p", field: "product", label: f.product_type });
  (f.materials ?? []).forEach((m, i) => chips.push({ key: `m${i}`, field: "materials", label: m }));
  if (brief.target_landed_cost_max_vnd) chips.push({ key: "c", field: "cost", label: `về tay ≤ ${formatVndCompact(brief.target_landed_cost_max_vnd)}` });
  if (f.origins?.length) chips.push({ key: "o", field: "origins", label: f.origins.map((o) => ORIGIN_LABEL[o] ?? o).join(", ") });
  if (f.min_rating) chips.push({ key: "r", field: "rating", label: `đánh giá ≥ ${String(f.min_rating).replace(".", ",")}` });
  (f.must_not ?? []).forEach((m, i) => chips.push({ key: `n${i}`, field: "must_not", label: m }));
  (f.prefer ?? []).forEach((m, i) => chips.push({ key: `f${i}`, field: "prefer", label: m }));
  const zh = brief.keywords_translated.zh ?? [];
  const ja = brief.keywords_translated.ja ?? [];
  return (
    <div className="flex flex-col gap-2">
      <ChipRow className="md:flex-wrap">
        {chips.map((c) => (
          <Chip key={c.key} selected onClick={() => onEdit(c.field)}>
            {c.label}
          </Chip>
        ))}
        <Chip icon={<Pencil aria-hidden />} onClick={() => onEdit("product")}>
          Sửa
        </Chip>
      </ChipRow>
      {zh.length || ja.length ? (
        <p className="text-[13px] text-ink-2">
          Từ khoá:{" "}
          {zh.length ? (
            <button type="button" className="underline decoration-line-strong underline-offset-2" onClick={() => onEdit("kw_zh")} lang="zh">
              {zh.join(" · ")}
            </button>
          ) : null}
          {zh.length && ja.length ? " / " : null}
          {ja.length ? (
            <button type="button" className="underline decoration-line-strong underline-offset-2" onClick={() => onEdit("kw_ja")} lang="ja">
              {ja.join(" · ")}
            </button>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
