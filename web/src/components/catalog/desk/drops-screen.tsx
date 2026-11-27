"use client";

import { CalendarPlus, Hourglass } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardLink } from "@/components/ui/card";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/field";
import { Sheet } from "@/components/ui/overlay";
import { PageHeader } from "@/components/ui/page-header";
import { DROP_STATUS_LABELS, useCreateDrop, useDeskDrops, type DropStatus } from "@/lib/api/catalog";
import { formatDateTime, formatDayMonth } from "@/lib/format";
import { PRODUCT_SECTIONS } from "@/lib/desk-sections";

export const DROP_TONE: Record<DropStatus, BadgeTone> = {
  draft: "outline",
  pending_review: "warning",
  scheduled: "accent",
  open: "success",
  closed: "neutral",
  sourcing: "neutral",
  arriving: "neutral",
  fulfilling: "neutral",
  completed: "neutral",
  cancelled: "outline",
};

/** Ô ngày giờ (giờ máy, tức giờ Việt Nam) ↔ ISO. */
export function toLocalInput(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export function fromLocalInput(v: string) {
  return v ? new Date(v).toISOString() : null;
}

/** Đợt bán (e3): tạo đợt nháp, thêm món, rồi mở (qua hàng chờ duyệt nếu người phụ bấm). */
export function DropsScreen() {
  const { data, isPending, error } = useDeskDrops();
  const create = useCreateDrop();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [closes, setCloses] = useState("");
  const [arrival, setArrival] = useState("");
  const [description, setDescription] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { title: title.trim(), description: description.trim() || null, closes_at: fromLocalInput(closes), expected_arrival_date: arrival || null, items: [] },
      { onSuccess: (d) => router.push(`/desk/san-pham/dot/${d.id}`) },
    );
  }

  const rows = data?.items ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        sections={PRODUCT_SECTIONS}
        active="drops"
        actions={
          <Button size="sm" icon={<CalendarPlus className="size-4" />} onClick={() => setOpen(true)}>
            Tạo đợt
          </Button>
        }
      />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được đợt bán" description={error.message} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<Hourglass />} title="Chưa có đợt nào" description="Tạo đợt đầu tiên rồi thêm các món đã lên kệ." />
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((d) => {
            const total = d.items.reduce((s, i) => s + (i.slots_total ?? 0), 0);
            const reserved = d.items.reduce((s, i) => s + i.slots_reserved, 0);
            return (
              <li key={d.id}>
                <CardLink href={`/desk/san-pham/dot/${d.id}`} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[15px] font-semibold">
                      {d.label} · {d.title}
                    </p>
                    <p className="text-[13px] text-ink-2">
                      {d.items.length} món{total ? ` · ${reserved}/${total} suất` : ""}
                      {d.closes_at ? ` · hạn ${formatDateTime(d.closes_at)}` : ""}
                      {d.expected_arrival_date ? ` · về ${formatDayMonth(d.expected_arrival_date)}` : ""}
                      {d.reminder_count ? ` · ${d.reminder_count} người chờ nhắc` : ""}
                    </p>
                  </div>
                  <Badge tone={DROP_TONE[d.status]}>{DROP_STATUS_LABELS[d.status]}</Badge>
                </CardLink>
              </li>
            );
          })}
        </ul>
      )}
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Tạo đợt mới"
        footer={
          <Button type="submit" form="new-drop" block loading={create.isPending} disabled={title.trim().length < 2}>
            Tạo đợt nháp
          </Button>
        }
      >
        <form id="new-drop" onSubmit={submit} className="flex flex-col gap-3">
          <Input label="Tên đợt" placeholder="vd. Đồ bếp gọn cho nhà nhỏ" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
          <Textarea label="Giới thiệu ngắn" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          <Input label="Hạn chót đặt" type="datetime-local" value={closes} onChange={(e) => setCloses(e.target.value)} />
          <Input label="Ngày hàng về dự kiến" type="date" value={arrival} onChange={(e) => setArrival(e.target.value)} />
        </form>
      </Sheet>
    </div>
  );
}
