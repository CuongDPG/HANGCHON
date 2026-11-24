"use client";

import { Check, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Button, EmptyState, Input, Sheet, SkeletonList } from "@/components/ui";
import { useCustomers, type CustomerItem, type CustomerSegment } from "@/lib/api/crm";
import { cn } from "@/lib/cn";
import { formatVnd } from "@/lib/format";

type CustomerPickerProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  /** Chọn nhiều khách (mời thử hàng); mặc định chọn một. */
  multiple?: boolean;
  segment?: CustomerSegment;
  confirmLabel?: string;
  loading?: boolean;
  onPick: (customers: CustomerItem[]) => void;
};

/** Sheet tìm và chọn khách trong sổ khách (tìm không dấu theo tên, số điện thoại, phần trước @ của email). */
export function CustomerPicker({ open, onClose, title, description, multiple, segment = "all", confirmLabel, loading, onPick }: CustomerPickerProps) {
  const [q, setQ] = useState("");
  const query = useDeferredValue(q);
  const [picked, setPicked] = useState<CustomerItem[]>([]);
  const { data, isPending, error } = useCustomers({ q: query, segment, size: 30 });

  function toggle(c: CustomerItem) {
    if (!multiple) {
      onPick([c]);
      return;
    }
    setPicked((p) => (p.some((x) => x.id === c.id) ? p.filter((x) => x.id !== c.id) : [...p, c]));
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        multiple ? (
          <Button block disabled={!picked.length} loading={loading} onClick={() => onPick(picked)}>
            {confirmLabel ?? "Chọn"} {picked.length ? `(${picked.length})` : ""}
          </Button>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-3">
        <Input
          aria-label="Tìm khách"
          placeholder="Tên, số điện thoại, email…"
          leading={<Search aria-hidden />}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {isPending ? (
          <SkeletonList rows={3} />
        ) : error ? (
          <EmptyState tone="error" title="Chưa tải được sổ khách" description={error.message} />
        ) : data.items.length === 0 ? (
          <EmptyState icon={<Search />} title="Không thấy khách nào" description="Thử tìm bằng số điện thoại hoặc tên không dấu." />
        ) : (
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
            {data.items.map((c) => {
              const on = picked.some((x) => x.id === c.id);
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    aria-pressed={multiple ? on : undefined}
                    onClick={() => toggle(c)}
                    className={cn("flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-soft-2", on && "bg-accent-wash")}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-medium">{c.name || c.phone || "Khách"}</span>
                      <span className="block truncate text-[13px] text-ink-2">
                        {[c.phone, c.order_count ? `${c.order_count} đơn · ${formatVnd(c.total_spent_vnd)}` : "Chưa mua", c.opted_out ? "Từ chối nhận tin" : null]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    {on ? <Check className="size-5 text-accent" aria-hidden /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Sheet>
  );
}
