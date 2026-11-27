"use client";

import { Mic, Settings2, Sparkles, ListChecks, Stamp } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type DragEvent } from "react";
import {
  Button,
  Card,
  EmptyState,
  IconButton,
  IconLink,
  InlineSelect,
  Input,
  PageHeader,
  Sheet,
  SkeletonList,
  Tabs,
  notifyInfo,
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
import {
  BOARD_PAGE,
  BOARD_SORT_KEY,
  BOARD_SORT_OPTIONS,
  isBoardSort,
  pageOf,
  sortFromParam,
  sortParam,
  type BoardSort,
} from "./board-paging";
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
  // cách xếp: URL (?xep=moi|cu) là nguồn chính; thiếu thì lấy lựa chọn nhớ trên máy này
  const sort: BoardSort = sortFromParam(params.get("xep")) ?? "manual";
  const { data, isPending, error, refetch } = useBoard(undefined, sort);
  const move = useMoveStage();
  const [rejecting, setRejecting] = useState<BoardCard | null>(null);
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [quickNote, setQuickNote] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<{ stage: Stage; index: number } | null>(null);
  const [shown, setShown] = useState<Partial<Record<Stage, number>>>({});
  const shownOf = (s: Stage) => shown[s] ?? BOARD_PAGE;
  const showMore = (s: Stage) => setShown((v) => ({ ...v, [s]: (v[s] ?? BOARD_PAGE) + BOARD_PAGE }));

  function replaceQuery(patch: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  function setTab(t: Stage) {
    replaceQuery({ tab: t });
  }

  function setSort(s: BoardSort) {
    try {
      window.localStorage.setItem(BOARD_SORT_KEY, s);
    } catch {
      // trình duyệt chặn localStorage: vẫn đổi được qua URL
    }
    replaceQuery({ xep: sortParam(s) });
  }

  // vào trang (kể cả quay lại từ menu, trang được giữ ẩn) mà URL không có ?xep: áp cách xếp chị chọn lần trước trên máy này
  const xepParam = params.get("xep");
  useEffect(() => {
    if (xepParam) return;
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(BOARD_SORT_KEY);
    } catch {
      return;
    }
    if (isBoardSort(stored) && stored !== "manual") replaceQuery({ xep: sortParam(stored) });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy lại khi ?xep đổi
  }, [xepParam]);

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
    if (card.stage === stage && sort !== "manual") {
      // đang xếp theo thời gian: không đổi chỗ trong cột được, mời chị chuyển sang «Tự xếp» (thứ tự cũ vẫn giữ nguyên)
      const from = data!.columns[stage].findIndex((c) => c.id === card.id);
      if (index !== undefined && index !== from && index !== from + 1) {
        notifyInfo("Đang xếp theo thời gian nên chưa đổi chỗ trong cột được.", { label: "Chuyển sang Tự xếp", onClick: () => setSort("manual") });
      }
      return;
    }
    if (card.stage === stage) {
      const col = data!.columns[stage];
      const from = col.findIndex((c) => c.id === card.id);
      if (index === undefined || index === from || index === from + 1) return;
      void moveTo(card, stage, index > from ? index - 1 : index);
    } else {
      // đang xếp theo thời gian thì không ghi vị trí: thẻ nằm theo cách xếp đang chọn
      const keepPosition = sort === "manual" && stage !== "rejected" && stage !== "selected";
      void moveTo(card, stage, keepPosition ? index : undefined);
    }
  }

  function onDragOverColumn(e: DragEvent<HTMLElement>, stage: Stage) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    // cột tự cuộn khi kéo thẻ tới gần mép trên/dưới (dragover bắn liên tục khi đang giữ chuột)
    const list = e.currentTarget.querySelector<HTMLElement>("[data-column-list]");
    if (list) {
      const r = list.getBoundingClientRect();
      if (e.clientY < r.top + 48) list.scrollTop -= 16;
      else if (e.clientY > r.bottom - 48) list.scrollTop += 16;
    }
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
            {data ? (
              <Button size="sm" variant="secondary" icon={<Mic className="size-4" aria-hidden />} onClick={() => setQuickNote(true)}>
                <span>
                  Ghi nhanh<span className="max-md:hidden">, AI xếp vào món</span>
                </span>
              </Button>
            ) : null}
            <InlineSelect appearance="inline" aria-label="Xếp thẻ trong cột" value={sort} onChange={setSort} options={BOARD_SORT_OPTIONS} />
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
          {/* Điện thoại: tab */}
          <div className="flex flex-col gap-3 md:hidden">
            <Tabs
              aria-label="Cột của bàn chọn"
              value={tab}
              onChange={setTab}
              items={STAGES.map((s) => ({ value: s, label: STAGE_LABELS[s], count: data.counts[s] }))}
            />
            {tab === "rejected" ? <RejectionSummary /> : null}
            <Column cards={data.columns[tab]} total={data.counts[tab]} stage={tab} sort={sort} shown={shownOf(tab)} onMore={() => showMore(tab)} />
          </div>

          {/* Máy tính: kanban kéo thả */}
          <div className="-mx-4 overflow-x-auto px-4 max-md:hidden md:mx-0 md:px-0">
            <div className="grid min-w-[880px] grid-cols-5 gap-2">
              {STAGES.map((s) => {
                const page = pageOf(data.columns[s], shownOf(s), data.counts[s]);
                return (
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
                    {/* tên cột + số luôn hiện; danh sách cuộn riêng trong cột */}
                    <div data-column-list className="-mx-1.5 flex max-h-[calc(100dvh-11rem)] min-h-0 flex-col gap-2 overflow-y-auto overscroll-contain px-1.5 pt-1.5 pb-0.5">
                      {page.visible.map((c, i) => (
                        <div key={c.id} className="relative">
                          {over?.stage === s && over.index === i && dragId && sort === "manual" ? (
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
                      <MoreCards more={page.more} notLoaded={page.notLoaded} sort={sort} onMore={() => showMore(s)} compact />
                    </div>
                  </section>
                );
              })}
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

type ColumnProps = { cards: BoardCard[]; total: number; stage: Stage; sort: BoardSort; shown: number; onMore: () => void };

function Column({ cards, total, stage, sort, shown, onMore }: ColumnProps) {
  if (!cards.length) return <EmptyState icon={<Stamp />} title={`Chưa có món nào ở «${STAGE_LABELS[stage]}»`} description={EMPTY[stage]} />;
  const page = pageOf(cards, shown, total);
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {page.visible.map((c) => (
          <li key={c.id} className="flex flex-col gap-1">
            <CandidateCard card={c} />
            <ContentQuickLink card={c} />
          </li>
        ))}
      </ul>
      <MoreCards more={page.more} notLoaded={page.notLoaded} sort={sort} onMore={onMore} />
    </div>
  );
}

/** «Xem thêm (n)» cuối cột; cột vượt trần tải thì nói rõ còn bao nhiêu món chưa hiện. */
function MoreCards({
  more,
  notLoaded,
  sort,
  onMore,
  compact = false,
}: {
  more: number;
  notLoaded: number;
  sort: BoardSort;
  onMore: () => void;
  compact?: boolean;
}) {
  return (
    <>
      {more > 0 ? (
        <Button size="sm" variant="secondary" block={compact} className={compact ? undefined : "self-center"} onClick={onMore}>
          Xem thêm ({more})
        </Button>
      ) : null}
      {more === 0 && notLoaded > 0 ? (
        <p className="px-1 text-[12.5px] text-ink-3">
          Còn {notLoaded} món {sort === "oldest" ? "mới" : "cũ"} hơn chưa hiện trên bàn chọn.
        </p>
      ) : null}
    </>
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
