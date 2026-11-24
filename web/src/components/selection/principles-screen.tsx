"use client";

import { ListChecks, PenLine, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Chip,
  ChipRow,
  EmptyState,
  IconButton,
  InlineSelect,
  PageHeader,
  SectionLabel,
  Segmented,
  Sheet,
  SkeletonList,
  Switch,
  Textarea,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import {
  PRINCIPLE_LABELS,
  useCategories,
  useDeletePrinciple,
  usePrinciples,
  useSavePrinciple,
  useTogglePrinciple,
  type Category,
  type Principle,
  type PrincipleKind,
} from "@/lib/api/selection";

const KINDS: PrincipleKind[] = ["must", "must_not", "prefer", "avoid"];
const ALL = "__all";
const GENERAL = "__general";

/** Bộ nguyên tắc của chị (c5) theo nhóm hàng; AI dùng để lọc ứng viên từ đầu. */
export function PrinciplesScreen() {
  const { data, isPending, error } = usePrinciples();
  const cats = useCategories();
  const [filter, setFilter] = useState<string>(ALL);
  const [editing, setEditing] = useState<Principle | "new" | null>(null);
  const catName = (id: string | null) => (id ? (cats.data?.find((c) => c.id === id)?.name ?? "Nhóm khác") : "Mọi nhóm hàng");

  const shown = (data ?? []).filter((p) =>
    filter === ALL ? true : filter === GENERAL ? p.category_id === null : p.category_id === filter || p.category_id === null,
  );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Nguyên tắc chọn hàng"
        description="AI dùng các nguyên tắc này để lọc từ đầu khi săn hàng. Nguyên tắc chung áp cho mọi nhóm."
        backHref="/desk/ban-chon"
        actions={
          <Button size="sm" icon={<Plus className="size-4" aria-hidden />} onClick={() => setEditing("new")}>
            Thêm
          </Button>
        }
      />
      <ChipRow>
        <Chip selected={filter === ALL} onClick={() => setFilter(ALL)} count={data?.length}>
          Tất cả
        </Chip>
        <Chip selected={filter === GENERAL} onClick={() => setFilter(GENERAL)}>
          Chung
        </Chip>
        {cats.data?.map((c) => (
          <Chip key={c.id} selected={filter === c.id} onClick={() => setFilter(c.id)}>
            {c.name}
          </Chip>
        ))}
      </ChipRow>
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được nguyên tắc" description={error.message} />
      ) : !shown.length ? (
        <EmptyState
          icon={<ListChecks />}
          title="Chưa có nguyên tắc nào"
          description="Ví dụ: «Không chọn hàng có pin», «Ưu tiên inox 304 cho đồ bếp»."
          action={<Button onClick={() => setEditing("new")}>Thêm nguyên tắc</Button>}
        />
      ) : (
        KINDS.map((k) => {
          const items = shown.filter((p) => p.kind === k);
          if (!items.length) return null;
          return (
            <section key={k} className="flex flex-col gap-2">
              <SectionLabel>{PRINCIPLE_LABELS[k]}</SectionLabel>
              <ul className="flex flex-col gap-2">
                {items.map((p) => (
                  <PrincipleRow key={p.id} p={p} catName={catName(p.category_id)} onEdit={() => setEditing(p)} />
                ))}
              </ul>
            </section>
          );
        })
      )}
      <Sheet open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Thêm nguyên tắc" : "Sửa nguyên tắc"}>
        {editing !== null ? (
          <PrincipleForm
            key={editing === "new" ? "new" : editing.id}
            initial={editing === "new" ? null : editing}
            categories={cats.data ?? []}
            defaultCategory={filter !== ALL && filter !== GENERAL ? filter : null}
            onClose={() => setEditing(null)}
          />
        ) : null}
      </Sheet>
    </div>
  );
}

function PrincipleRow({ p, catName, onEdit }: { p: Principle; catName: string; onEdit: () => void }) {
  const toggle = useTogglePrinciple();
  const del = useDeletePrinciple();
  const confirm = useConfirm();
  return (
    <li>
      <Card className={p.is_active ? undefined : "opacity-60"}>
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[15px]">{p.text}</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <Badge tone={p.category_id ? "accent" : "neutral"}>{catName}</Badge>
              {p.source === "ai_suggested" ? <Badge tone="warning">AI gợi ý</Badge> : null}
              {!p.is_active ? <Badge tone="outline">Đang tắt</Badge> : null}
            </div>
          </div>
          <IconButton size="sm" label="Sửa nguyên tắc" icon={<PenLine />} onClick={onEdit} />
          <IconButton
            size="sm"
            label="Xoá nguyên tắc"
            icon={<Trash2 />}
            onClick={async () => {
              if (await confirm({ title: "Xoá nguyên tắc này?", message: p.text, confirmLabel: "Xoá", tone: "danger" })) {
                await del.mutateAsync(p.id);
                notifySuccess("Đã xoá");
              }
            }}
          />
        </div>
        <Switch
          className="mt-2 border-t border-line pt-2"
          label="Đang áp dụng"
          checked={p.is_active}
          onChange={(v) => toggle.mutate({ id: p.id, is_active: v })}
        />
      </Card>
    </li>
  );
}

function PrincipleForm({
  initial,
  categories,
  defaultCategory,
  onClose,
}: {
  initial: Principle | null;
  categories: Category[];
  defaultCategory: string | null;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<PrincipleKind>(initial?.kind ?? "must");
  const [text, setText] = useState(initial?.text ?? "");
  const [cat, setCat] = useState<string>(initial ? (initial.category_id ?? GENERAL) : (defaultCategory ?? GENERAL));
  const [error, setError] = useState<string | null>(null);
  const save = useSavePrinciple();
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        if (text.trim().length < 3) {
          setError("Chị ghi rõ hơn một chút nhé.");
          return;
        }
        await save.mutateAsync({ id: initial?.id, kind, text: text.trim(), category_id: cat === GENERAL ? null : cat });
        notifySuccess(initial ? "Đã sửa nguyên tắc" : "Đã thêm nguyên tắc");
        onClose();
      }}
    >
      <Segmented aria-label="Loại nguyên tắc" value={kind} onChange={setKind} block options={KINDS.map((k) => ({ value: k, label: PRINCIPLE_LABELS[k] }))} />
      <Textarea label="Nguyên tắc" value={text} onChange={(e) => setText(e.target.value)} error={error} placeholder="Ví dụ: đồ tiếp xúc thực phẩm phải ghi rõ chất liệu" />
      <InlineSelect
        label="Áp cho nhóm hàng"
        value={cat}
        onChange={setCat}
        options={[{ value: GENERAL, label: "Mọi nhóm hàng" }, ...categories.map((c) => ({ value: c.id, label: c.name }))]}
      />
      <div className="flex justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={save.isPending}>
          Lưu
        </Button>
      </div>
    </form>
  );
}
