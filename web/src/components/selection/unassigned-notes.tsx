"use client";

import { DateTime, InlineSelect, SectionLabel, notifySuccess } from "@/components/ui";
import { useUnassignedNotes, useUpdateNote, type BoardCard } from "@/lib/api/selection";

/** Ghi chú AI chưa chắc thuộc món nào: chị chọn món cho nó. */
export function UnassignedNotes({ cards }: { cards: BoardCard[] }) {
  const { data } = useUnassignedNotes();
  const update = useUpdateNote();
  if (!data?.length) return null;
  return (
    <section className="flex flex-col gap-2">
      <SectionLabel>Chưa xếp được vào món · {data.length}</SectionLabel>
      <ul className="flex flex-col gap-2">
        {data.map((n) => (
          <li key={n.id} className="rounded-md border border-line bg-surface p-3">
            <p className="text-[15px]">«{n.text ?? "Ảnh, ghi âm"}»</p>
            <p className="mt-0.5 text-[13px] text-ink-2">
              <DateTime value={n.recorded_at} format="relative" />
            </p>
            <div className="mt-2">
              <InlineSelect
                aria-label="Xếp vào món"
                placeholder="Xếp vào món…"
                value={null}
                options={cards.map((c) => ({ value: c.id, label: c.title }))}
                onChange={async (id) => {
                  await update.mutateAsync({ id: n.id, candidate_id: id });
                  notifySuccess("Đã xếp ghi chú vào món");
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
