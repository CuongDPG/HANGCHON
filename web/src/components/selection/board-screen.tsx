"use client";

import { Mic, Settings2, Sparkles, ListChecks, Stamp } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type DragEvent } from "react";
import {
  Button,
  Card,
  EmptyState,
  IconButton,
  IconLink,
  Input,
  PageHeader,
  Sheet,
  SkeletonList,
  Tabs,
  notifySuccess,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  STAGES,
  STAGE_LABELS,
  useBoard,
  useMoveStage,
  useRejectionStats,
  useSelectionSettings,
  useUpdateSelectionSettings,
  type BoardCard,
  type Decision,
  type Stage,
} from "@/lib/api/selection";
import { CandidateCard, ContentQuickLink } from "./candidate-card";
import { NoteComposer } from "./note-composer";
import { ReasonsCard } from "./reasons-card";
import { RejectSheet } from "./reject-sheet";
import { UnassignedNotes } from "./unassigned-notes";

const EMPTY: Record<Stage, string> = {
  candidate: "Ứng viên chị đánh dấu từ Săn hàng sẽ nằm ở đây.",
  sample: "Món chị quyết mua mẫu sẽ nằm ở đây; AI soạn sẵn đơn đặt mẫu để chị duyệt.",
  trial: "Món đang dùng thử. Chị nói vài câu mỗi ngày, AI ghi lại.",
  selected: "Món đã đóng dấu chọn.",
  rejected: "Món đã loại, kèm lý do cho trang Hồ sơ chọn.",
};

/** Bảng chọn (c1): tab trên điện thoại, kanban kéo thả trên máy tính. */
export function BoardScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tabParam = params.get("tab") as Stage | null;
  const tab: Stage = tabParam && STAGES.includes(tabParam) ? tabParam : "trial";
  const { data, isPending, error, refetch } = useBoard();
  const move = useMoveStage();
  const [rejecting, setRejecting] = useState<BoardCard | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [quickNote, setQuickNote] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<{ stage: Stage; index: number } | null>(null);

  function setTab(t: Stage) {
    router.replace(`${pathname}?tab=${t}`, { scroll: false });
  }

  async function moveTo(card: BoardCard, to: Stage, position?: number) {
    if (to === card.stage && position === undefined) return;
    if (to === "rejected" && card.stage !== "rejected") {
      setRejecting(card);
      return;
    }
    const r = await move.mutateAsync({ id: card.id, to, position });
    if (to !== card.stage) notifySuccess(`Đã chuyển «${card.title}» sang ${STAGE_LABELS[to]}`);
    if (to === "selected" && r.decision) setSelectedDecision(r.decision);
  }

  function onDrop(e: DragEvent, stage: Stage) {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/hangchon-card") || dragId;
    const card = id ? Object.values(data?.columns ?? {}).flat().find((c) => c.id === id) : undefined;
    const index = over?.stage === stage ? over.index : undefined;
    setDragId(null);
    setOver(null);
    if (!card) return;
    if (card.stage === stage) {
      const col = data!.columns[stage];
      const from = col.findIndex((c) => c.id === card.id);
      if (index === undefined || index === from || index === from + 1) return;
      void moveTo(card, stage, index > from ? index - 1 : index);
    } else {
      void moveTo(card, stage, stage === "rejected" || stage === "selected" ? undefined : index);
    }
  }

  function onDragOverColumn(e: DragEvent<HTMLElement>, stage: Stage) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const cards = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-card-id]"));
    let index = cards.length;
    for (let i = 0; i < cards.length; i++) {
      const r = cards[i].getBoundingClientRect();
      if (e.clientY < r.top + r.height / 2) {
        index = i;
        break;
      }
    }
    if (over?.stage !== stage || over.index !== index) setOver({ stage, index });
  }

  const selectedTotal = data?.counts.selected ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Bàn chọn"
        eyebrow={data ? `${selectedTotal} món đã chọn` : undefined}
        actions={
          <>
            <IconLink href="/desk/ban-chon/nguyen-tac" label="Bộ nguyên tắc của chị" icon={<ListChecks />} />
            <IconLink href="/desk/ban-chon/gu" label="AI hiểu gu chị thế nào" icon={<Sparkles />} />
            <IconButton label="Cài đặt bàn chọn" icon={<Settings2 />} onClick={() => setSettingsOpen(true)} />
          </>
        }
      />

      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được bàn chọn"
          description={error.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" icon={<Mic className="size-4" aria-hidden />} onClick={() => setQuickNote(true)}>
              Ghi nhanh, AI xếp vào món
            </Button>
            <p className="text-[13px] text-ink-2 max-md:hidden">Kéo thẻ sang cột khác để chuyển; loại thì ghi lý do.</p>
          </div>

          {/* Điện thoại: tab */}
          <div className="flex flex-col gap-3 md:hidden">
            <Tabs
              aria-label="Cột của bàn chọn"
              value={tab}
              onChange={setTab}
              items={STAGES.map((s) => ({ value: s, label: STAGE_LABELS[s], count: data.counts[s] }))}
            />
            {tab === "rejected" ? <RejectionSummary /> : null}
            <Column cards={data.columns[tab]} stage={tab} />
          </div>

          {/* Máy tính: kanban kéo thả */}
          <div className="-mx-4 overflow-x-auto px-4 max-md:hidden md:mx-0 md:px-0">
            <div className="grid min-w-[880px] grid-cols-5 gap-2">
              {STAGES.map((s) => (
                <section
                  key={s}
                  aria-label={STAGE_LABELS[s]}
                  onDragOver={(e) => onDragOverColumn(e, s)}
                  onDragLeave={(e) => {
                    if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(null);
                  }}
                  onDrop={(e) => onDrop(e, s)}
                  className={cn(
                    "flex min-h-80 min-w-0 flex-col gap-2 rounded-md bg-soft/60 p-1.5 transition-colors",
                    over?.stage === s && dragId && "bg-accent-wash outline-2 outline-dashed outline-accent/40",
                  )}
                >
                  <h2 className="flex items-center justify-between px-1 pt-1 font-sans text-[13px] font-semibold tracking-[0.06em] text-ink-2 uppercase">
                    {STAGE_LABELS[s]}
                    <span className="rounded-sm bg-surface px-1.5 text-[12px] tabular-nums">{data.counts[s]}</span>
                  </h2>
                  {s === "rejected" ? <RejectionSummary compact /> : null}
                  {data.columns[s].map((c, i) => (
                    <div key={c.id} className="relative">
                      {over?.stage === s && over.index === i && dragId ? (
                        <div aria-hidden className="absolute -top-1.5 right-1 left-1 h-0.5 rounded-full bg-accent" />
                      ) : null}
                      <CandidateCard
                        card={c}
                        compact
                        draggable
                        dragging={dragId === c.id}
                        onDragStart={(e) => {
                          e.dataTransfer.setData("text/hangchon-card", c.id);
                          e.dataTransfer.effectAllowed = "move";
                          setDragId(c.id);
                        }}
                      />
                      <ContentQuickLink card={c} compact />
                    </div>
                  ))}
                  {!data.columns[s].length ? <p className="px-1 py-4 text-[13px] text-ink-3">{EMPTY[s]}</p> : null}
                </section>
              ))}
            </div>
          </div>
        </>
      )}

      <RejectSheet candidate={rejecting} onClose={() => setRejecting(null)} />
      <Sheet
        open={!!selectedDecision}
        onClose={() => setSelectedDecision(null)}
        title="Đã đóng dấu chọn"
        description="AI soạn lý do từ ghi chú thử của chị. Chị sửa lời rồi chốt, hoặc để sau."
      >
        {selectedDecision ? <ReasonsCard decision={selectedDecision} /> : null}
      </Sheet>
      <Sheet open={quickNote} onClose={() => setQuickNote(false)} title="Ghi nhanh" description="Chị nói về món nào cũng được, AI tự xếp vào đúng món đang thử.">
        {quickNote ? (
          <div className="flex flex-col gap-4">
            <NoteComposer candidateId={null} compact />
            <UnassignedNotes cards={[...(data?.columns.trial ?? []), ...(data?.columns.sample ?? [])]} />
          </div>
        ) : null}
      </Sheet>
      <SettingsSheet open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

function Column({ cards, stage }: { cards: BoardCard[]; stage: Stage }) {
  if (!cards.length) return <EmptyState icon={<Stamp />} title={`Chưa có món nào ở «${STAGE_LABELS[stage]}»`} description={EMPTY[stage]} />;
  return (
    <ul className="flex flex-col gap-2">
      {cards.map((c) => (
        <li key={c.id} className="flex flex-col gap-1">
          <CandidateCard card={c} />
          <ContentQuickLink card={c} />
        </li>
      ))}
    </ul>
  );
}

/** «21 mẫu loại: rò nước 8…» (c4). */
function RejectionSummary({ compact = false }: { compact?: boolean }) {
  const { data } = useRejectionStats();
  if (!data?.total) return null;
  if (compact) return <p className="px-1 text-[12.5px] text-ink-2">{data.summary}</p>;
  return (
    <Card tone="soft">
      <p className="text-[15px] font-semibold">{data.total} mẫu đã loại</p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[14px] text-ink-2">
        {data.groups.map((g) => (
          <li key={g.key}>
            {g.label} <span className="font-semibold text-ink tabular-nums">{g.count}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function SettingsSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const settings = useSelectionSettings();
  const save = useUpdateSelectionSettings();
  return (
    <Sheet open={open} onClose={onClose} title="Cài đặt bàn chọn">
      {open && settings.data ? (
        <form
          className="flex flex-col gap-4"
          onSubmit={async (e) => {
            e.preventDefault();
            const v = Number(new FormData(e.currentTarget).get("trial_days"));
            await save.mutateAsync({ trial_days: v });
            notifySuccess("Đã lưu số ngày thử");
            onClose();
          }}
        >
          <Input
            name="trial_days"
            type="number"
            min={1}
            max={90}
            label="Số ngày thử mỗi món"
            hint="Thanh tiến độ «ngày thử thứ n/14» trên thẻ."
            defaultValue={settings.data.trial_days}
            trailing="ngày"
          />
          <Button type="submit" loading={save.isPending} className="self-end">
            Lưu
          </Button>
        </form>
      ) : null}
    </Sheet>
  );
}
