"use client";

import { ChevronRight, Printer, Radio, Type } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  InlineSelect,
  Input,
  PageHeader,
  SectionLabel,
  Segmented,
  SkeletonList,
  notifySuccess,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { useCreateLivestream, useLivestream, useLivestreamAction, useLivestreams, usePickDrops, usePickProducts, type Livestream } from "@/lib/api/content";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import { CONTENT_SECTIONS } from "@/lib/desk-sections";
import { CONTENT_SETTINGS } from "./shared";

const STATUS: Record<Livestream["status"], { label: string; tone: "neutral" | "warning" | "success" | "accent" }> = {
  drafting: { label: "AI đang soạn", tone: "accent" },
  pending_review: { label: "Chờ chị duyệt", tone: "warning" },
  approved: { label: "Đã duyệt", tone: "success" },
  used: { label: "Đã dùng", tone: "neutral" },
};

/** Kịch bản livestream (f8): danh sách + tạo mới từ đợt bán hoặc danh sách món. */
export function LivestreamScreen() {
  const { data, isPending, error } = useLivestreams();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={CONTENT_SECTIONS} active="livestream" settings={CONTENT_SETTINGS} />
      <CreateCard />
      <section className="flex flex-col gap-2">
        <SectionLabel>KỊCH BẢN</SectionLabel>
        {isPending ? (
          <SkeletonList rows={3} />
        ) : error ? (
          <EmptyState tone="error" title="Chưa tải được" description={error.message} />
        ) : !data?.items.length ? (
          <EmptyState icon={<Radio />} title="Chưa có kịch bản" description="Chọn một đợt bán hoặc vài món ở trên để AI soạn." />
        ) : (
          <ul className="flex flex-col gap-2">
            {data.items.map((s) => (
              <li key={s.id}>
                <Link href={`/desk/noi-dung/livestream/${s.id}`} className="flex items-center gap-3 rounded-md border border-line bg-surface p-3 hover:border-line-strong">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{s.title}</p>
                    <p className="text-[13px] text-ink-2">
                      {s.items.length} món · {s.faq.length} câu hỏi{s.scheduled_for ? ` · ${formatDateTime(s.scheduled_for)}` : ""}
                    </p>
                  </div>
                  <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>
                  <ChevronRight className="size-5 text-ink-3" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function CreateCard() {
  const drops = usePickDrops();
  const products = usePickProducts();
  const create = useCreateLivestream();
  const [mode, setMode] = useState<"drop" | "items">("drop");
  const [dropId, setDropId] = useState<string | null>(null);
  const [ids, setIds] = useState<string[]>([]);
  const [minutes, setMinutes] = useState<"20" | "30" | "45">("30");
  const [title, setTitle] = useState("");
  const ready = mode === "drop" ? !!dropId : ids.length > 0;
  return (
    <Card tone="soft" className="flex flex-col gap-3">
      <Segmented aria-label="Soạn từ" value={mode} onChange={setMode} options={[{ value: "drop", label: "Từ một đợt bán" }, { value: "items", label: "Chọn vài món" }]} />
      {mode === "drop" ? (
        <InlineSelect label="Đợt bán" value={dropId} onChange={setDropId} placeholder="Chọn đợt" options={(drops.data?.items ?? []).map((d) => ({ value: d.id, label: d.title, hint: d.code }))} />
      ) : (
        <div className="flex max-h-56 flex-col overflow-y-auto">
          {(products.data?.items ?? []).map((p) => (
            <Checkbox key={p.id} label={p.name} checked={ids.includes(p.id)} onChange={(e) => setIds((x) => (e.target.checked ? [...x, p.id] : x.filter((i) => i !== p.id)))} />
          ))}
        </div>
      )}
      <Input label="Tên buổi live (không bắt buộc)" value={title} onChange={(e) => setTitle(e.target.value)} />
      <Segmented aria-label="Thời lượng" value={minutes} onChange={setMinutes} options={[{ value: "20", label: "20 phút" }, { value: "30", label: "30 phút" }, { value: "45", label: "45 phút" }]} />
      <Button
        disabled={!ready}
        loading={create.isPending}
        onClick={() =>
          create.mutate(
            { title: title || undefined, drop_id: mode === "drop" ? dropId : null, product_ids: mode === "items" ? ids : [], minutes: Number(minutes) },
            { onSuccess: () => { notifySuccess("AI đã soạn kịch bản, chờ chị duyệt"); setTitle(""); setIds([]); } },
          )
        }
      >
        Soạn kịch bản
      </Button>
    </Card>
  );
}

/** Xem kịch bản: bản in hoặc chế độ đọc chữ to trên điện thoại khi đang live. */
export function LivestreamDetail({ id }: { id: string }) {
  const { data, isPending, error } = useLivestream(id);
  const act = useLivestreamAction();
  const { user: session } = useSession();
  const [big, setBig] = useState(false);
  const owner = session?.role === "owner";
  return (
    <div className={cn("flex flex-col gap-4", big && "text-[19px]")}>
      <PageHeader
        backHref="/desk/noi-dung/livestream"
        title={data?.title}
        loading={isPending}
        badge={data ? <Badge tone={STATUS[data.status].tone}>{STATUS[data.status].label}</Badge> : undefined}
        actions={
          <div className="flex gap-1.5 print:hidden">
            <Button size="sm" variant={big ? "primary" : "ghost"} icon={<Type className="size-4" aria-hidden />} onClick={() => setBig((x) => !x)}>
              Chữ to
            </Button>
            <Button size="sm" variant="ghost" icon={<Printer className="size-4" aria-hidden />} onClick={() => window.print()}>
              In
            </Button>
          </div>
        }
      />
      {isPending ? (
        <SkeletonList rows={5} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : data ? (
        <>
          {owner && data.status === "pending_review" ? (
            <Card tone="accent" className="flex flex-wrap items-center gap-2 print:hidden">
              <p className="flex-1 text-[14px]">AI soạn xong, chị đọc rồi duyệt. Muốn sửa thì trả lại kèm lời nhắn ở «Chờ duyệt».</p>
              <Button loading={act.isPending} onClick={() => act.mutate({ id, action: "approve" }, { onSuccess: () => notifySuccess("Đã duyệt kịch bản") })}>
                Duyệt kịch bản
              </Button>
            </Card>
          ) : null}
          {owner && data.status === "approved" ? (
            <Button variant="secondary" className="self-start print:hidden" loading={act.isPending} onClick={() => act.mutate({ id, action: "used" })}>
              Đánh dấu đã live xong
            </Button>
          ) : null}
          <section className="flex flex-col gap-2">
            <SectionLabel>DÀN Ý · {data.outline.reduce((a, s) => a + s.minutes, 0)} PHÚT</SectionLabel>
            <ol className="flex flex-col gap-1.5">
              {data.outline.map((s, i) => (
                <li key={i} className="flex gap-3 rounded-md bg-surface p-2.5">
                  <span className="w-12 shrink-0 font-semibold tabular-nums">{s.minutes}′</span>
                  <div>
                    <p className="font-semibold">{s.segment}</p>
                    <p className="text-ink-2">{s.notes}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
          <section className="flex flex-col gap-2">
            <SectionLabel>THỨ TỰ MÓN</SectionLabel>
            {data.items.map((it) => (
              <Card key={it.product_id} className="flex flex-col gap-1.5 break-inside-avoid">
                <p className="font-display text-[1.1em] font-bold">
                  {it.order}. {it.name}
                </p>
                <ul className="list-disc pl-5">
                  {it.talking_points.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
                {it.demo ? <p className="text-ink-2">Dùng thử trước máy: {it.demo}</p> : null}
                {it.price_note ? <p className="font-semibold">{it.price_note}</p> : null}
              </Card>
            ))}
          </section>
          <section className="flex flex-col gap-2">
            <SectionLabel>CÂU KHÁCH HAY HỎI</SectionLabel>
            <ul className="flex flex-col gap-2">
              {data.faq.map((f, i) => (
                <li key={i} className="rounded-md border border-line bg-surface p-3 break-inside-avoid">
                  <p className="font-semibold">
                    {f.q} {f.source === "khach_hoi" ? <Badge tone="accent">khách đã hỏi</Badge> : null}
                    {f.needs_review ? <Badge tone="warning">chị xem lại</Badge> : null}
                  </p>
                  <p className="text-ink-2">→ {f.a}</p>
                </li>
              ))}
            </ul>
          </section>
          {data.notes ? <p className="text-[14px] text-ink-2">Ghi chú: {data.notes}</p> : null}
          <p className="text-[12.5px] text-ink-3">Kịch bản có phần do AI soạn. Chị lên hình bằng bàn tay và giọng nói của mình — không dùng người số.</p>
        </>
      ) : null}
    </div>
  );
}
