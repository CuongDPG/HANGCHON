"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { AiActionButton } from "@/components/control/command-sheet";
import { Button } from "@/components/ui/button";
import { SectionLabel } from "@/components/ui/card";
import { IconButton } from "@/components/ui/icon-button";
import type { DeskProduct, ProductPatch } from "@/lib/api/catalog";

/**
 * Phần dùng chung của hai trình sửa sản phẩm: trang website (Nội dung → Website, `page-content-editor.tsx`) và
 * bán hàng (Sản phẩm, `product-editor.tsx`). Mỗi bên chỉ gửi các trường của mình (PATCH từng phần).
 */

/** Bản nháp theo dữ liệu máy chủ: dữ liệu đổi (vừa lưu, vừa tải) → làm mới bản nháp ngay trong lúc render. */
export function useServerDraft<D>(p: DeskProduct | undefined, toDraft: (p: DeskProduct) => D, toPatch: (d: D) => ProductPatch) {
  const [draft, setDraft] = useState<D | null>(null);
  const [source, setSource] = useState<DeskProduct | undefined>();
  if (p && p !== source) {
    setSource(p);
    setDraft(toDraft(p));
  }
  const dirty = !!(p && draft && JSON.stringify(toPatch(draft)) !== JSON.stringify(toPatch(toDraft(p))));
  return { draft, setDraft, dirty, reset: () => p && setDraft(toDraft(p)) };
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <SectionLabel>{title}</SectionLabel>
      {children}
    </section>
  );
}

/** Thanh «Có thay đổi chưa lưu» dính đáy, ngay trên thanh điều hướng; «Nói với AI» (chỉ icon) ở đầu thanh thay cho nút nổi. */
export function SaveBar({ saving, onReset, onSave }: { saving: boolean; onReset: () => void; onSave: () => void }) {
  return (
    <div className="sticky bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+8px)] z-10 md:bottom-4">
      <div className="flex items-center gap-2 rounded-md border border-line bg-surface p-2 shadow-pop">
        <AiActionButton />
        <span className="min-w-0 flex-1 text-[14px] text-ink-2">Có thay đổi chưa lưu</span>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onReset}>
            Bỏ
          </Button>
          <Button loading={saving} onClick={onSave}>
            Lưu
          </Button>
        </div>
      </div>
    </div>
  );
}

export function RowsEditor<T extends object>({
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
