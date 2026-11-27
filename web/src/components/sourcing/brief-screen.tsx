"use client";

import { AlertCircle, Columns3, Link2, Mic, RotateCw, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  InlineSelect,
  PageHeader,
  SectionLabel,
  Seal,
  Skeleton,
  SkeletonList,
  Switch,
  Textarea,
  notifyError,
  notifySuccess,
} from "@/components/ui";
import { useComparisons, useCreateComparison } from "@/lib/api/assessment";
import {
  isRunActive,
  useBrief,
  useBriefCandidates,
  usePatchBrief,
  useReinterpret,
  useRunBrief,
  type Brief,
  type BriefPatch,
} from "@/lib/api/sourcing";
import { BRIEF_STATUS } from "./brief-list";
import { CandidateRow } from "./candidate-row";
import { CriteriaChips } from "./criteria-chips";
import { CriteriaSheet, type CriteriaField } from "./criteria-sheet";
import { LinkSheet } from "./link-sheet";
import { RunProgress } from "./run-progress";
import { useSpeech } from "./use-speech";

const THRESHOLDS = ["60", "70", "75", "80", "85", "90"].map((v) => ({ value: v, label: `Từ ${v} điểm` }));

function ScheduleCard({ brief, onPatch, saving }: { brief: Brief; onPatch: (p: BriefPatch) => void; saving: boolean }) {
  return (
    <Card className="flex flex-col gap-3">
      <Switch
        label="Lưu đề này, chạy lại mỗi tuần"
        description={
          brief.is_scheduled && brief.next_run_at
            ? `Lần tới: ${new Date(brief.next_run_at).toLocaleDateString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}. Chỉ báo chị khi có món mới đạt ngưỡng.`
            : "AI tự tìm lại hằng tuần, chỉ báo chị khi có ứng viên mới đạt ngưỡng."
        }
        checked={brief.is_scheduled}
        disabled={saving || brief.status === "draft"}
        onChange={(on) => onPatch({ is_scheduled: on })}
      />
      {brief.is_scheduled ? (
        <InlineSelect
          label="Báo khi ứng viên mới đạt"
          value={String(brief.alert_min_score ?? 75)}
          onChange={(v) => onPatch({ alert_min_score: Number(v) })}
          options={THRESHOLDS}
          disabled={saving}
        />
      ) : null}
    </Card>
  );
}

function RetellSheetInline({ brief, onDone }: { brief: Brief; onDone: () => void }) {
  const [text, setText] = useState(brief.raw_text);
  const reinterpret = useReinterpret(brief.id);
  const speech = useSpeech((heard) => setText(heard));
  return (
    <Card tone="soft" className="flex flex-col gap-3">
      <Textarea label="Chị dặn lại" value={text} onChange={(e) => setText(e.target.value)} rows={3} error={speech.error ?? undefined} />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          icon={<Mic className="size-4" />}
          disabled={!speech.supported}
          onClick={() => (speech.listening ? speech.stop() : speech.start())}
        >
          {speech.listening ? "Dừng" : "Nói lại"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Huỷ
        </Button>
        <Button
          size="sm"
          className="ml-auto"
          icon={<Sparkles className="size-4" />}
          loading={reinterpret.isPending}
          disabled={text.trim().length < 3}
          onClick={() => reinterpret.mutate(text.trim(), { onSuccess: onDone, onError: notifyError })}
        >
          AI đọc lại
        </Button>
      </div>
    </Card>
  );
}

export function BriefScreen({ id }: { id: string }) {
  const router = useRouter();
  const { data: brief, isPending, error, refetch } = useBrief(id);
  const running = isRunActive(brief?.last_run);
  const candidates = useBriefCandidates(id, !!brief && !running, `${brief?.last_run?.id ?? ""}:${brief?.last_run?.status ?? ""}`);
  const patch = usePatchBrief(id);
  const run = useRunBrief(id);
  const compare = useCreateComparison();
  const comparisons = useComparisons(id);
  const [edit, setEdit] = useState<CriteriaField | null>(null);
  const [retell, setRetell] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);

  if (isPending)
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Đang tải">
        <PageHeader loading backHref="/desk/san-hang" />
        <Skeleton className="h-28 w-full" />
        <SkeletonList rows={4} />
      </div>
    );
  if (error || !brief)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Đề tìm" backHref="/desk/san-hang" />
        <EmptyState
          tone="error"
          title="Chưa tải được đề này"
          description={error?.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      </div>
    );

  const st = BRIEF_STATUS[brief.status];
  const items = candidates.data?.items ?? [];
  const unclear = brief.filters.unclear ?? [];
  const savePatch = (p: BriefPatch, done?: () => void) =>
    patch.mutate(p, {
      onSuccess: () => {
        done?.();
        notifySuccess("Đã lưu");
      },
      onError: notifyError,
    });
  const startRun = () => run.mutate(undefined, { onError: notifyError });
  const toggle = (cid: string) =>
    setPicked((cur) => (cur.includes(cid) ? cur.filter((x) => x !== cid) : cur.length >= 5 ? cur : [...cur, cid]));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        backHref="/desk/san-hang"
        badge={<Badge tone={st.tone}>{st.label}</Badge>}
        title={brief.title}
        actions={
          brief.candidate_count ? <Seal chosen={brief.selected_count} total={brief.candidate_count} size={36} /> : undefined
        }
      />

      <section className="flex flex-col gap-3" aria-label="Đề của chị">
        {retell ? (
          <RetellSheetInline brief={brief} onDone={() => setRetell(false)} />
        ) : (
          <Card className="flex flex-col gap-2">
            <p className="text-[15px] [text-wrap:pretty]">{brief.raw_text}</p>
            <button type="button" className="self-start text-[13px] font-medium text-accent" onClick={() => setRetell(true)}>
              Dặn lại
            </button>
          </Card>
        )}
        <SectionLabel>AI hiểu là</SectionLabel>
        {brief.interpretation ? <p className="-mt-1 text-sm text-ink-2 [text-wrap:pretty]">{brief.interpretation}</p> : null}
        {brief.interpretation ? (
          <CriteriaChips brief={brief} onEdit={setEdit} />
        ) : (
          <p className="text-sm text-review">AI đã đọc đề, phần hiểu đề đang chờ chị duyệt ở mục Chờ duyệt.</p>
        )}
        {unclear.length && brief.status === "draft" ? (
          <ul className="flex flex-col gap-1">
            {unclear.map((u) => (
              <li key={u} className="flex items-start gap-1.5 text-[13px] text-review">
                <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {u}
              </li>
            ))}
          </ul>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {brief.status === "draft" ? (
            <Button icon={<Search className="size-4" />} loading={run.isPending} onClick={startRun} disabled={!brief.interpretation}>
              Đúng rồi, tìm đi
            </Button>
          ) : brief.status === "active" || brief.status === "paused" ? (
            <Button variant="secondary" icon={<RotateCw className="size-4" />} loading={run.isPending || running} onClick={startRun}>
              Tìm lại
            </Button>
          ) : null}
          <Button variant="ghost" icon={<Link2 className="size-4" />} onClick={() => setLinkOpen(true)}>
            Thêm bằng link
          </Button>
        </div>
      </section>

      {brief.last_run ? (
        <Card tone="soft" flush className="px-4 py-3">
          <RunProgress run={brief.last_run} />
        </Card>
      ) : null}

      {brief.status !== "draft" ? (
        <section className="flex flex-col gap-3" aria-label="Ứng viên">
          <SectionLabel
            aside={
              items.length >= 2 ? (
                <Button
                  size="sm"
                  variant={picking ? "secondary" : "ghost"}
                  icon={<Columns3 className="size-4" />}
                  onClick={() => {
                    setPicking((v) => !v);
                    setPicked([]);
                  }}
                >
                  {picking ? "Thôi so sánh" : "So sánh"}
                </Button>
              ) : null
            }
          >
            {items.length ? `${items.length} ứng viên` : "Ứng viên"}
          </SectionLabel>
          {picking ? <p className="-mt-1 text-[13px] text-ink-2">Chọn 2–5 món để xếp cạnh nhau.</p> : null}
          {candidates.isPending || running ? (
            <SkeletonList rows={4} />
          ) : candidates.error ? (
            <EmptyState tone="error" title="Chưa tải được ứng viên" description={candidates.error.message} />
          ) : !items.length ? (
            <EmptyState
              icon={<Search />}
              title="Chưa có ứng viên"
              description={
                brief.last_run?.progress?.elsewhere_ids?.length
                  ? "Các món tìm được đều đã nằm ở đề khác của chị. Chị đổi từ khoá để tìm thêm nhé."
                  : "Chưa tìm thấy món nào khớp đề. Chị nới tiêu chí rồi tìm lại nhé."
              }
            />
          ) : (
            items.map((c) => (
              <CandidateRow key={c.id} c={c} selectable={picking} selected={picked.includes(c.id)} onToggle={() => toggle(c.id)} />
            ))
          )}
          {comparisons.data?.items.length ? (
            <p className="text-[13px] text-ink-2">
              Bảng so sánh đã lập:{" "}
              {comparisons.data.items.map((cmp, i) => (
                <span key={cmp.id}>
                  {i ? ", " : ""}
                  <Link className="font-medium text-accent underline-offset-2 hover:underline" href={`/desk/san-hang/so-sanh/${cmp.id}`}>
                    {new Date(cmp.created_at).toLocaleDateString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}
                  </Link>
                </span>
              ))}
            </p>
          ) : null}
        </section>
      ) : null}

      {brief.status !== "draft" ? <ScheduleCard brief={brief} saving={patch.isPending} onPatch={(p) => savePatch(p)} /> : null}

      {picking && picked.length ? (
        <div className="sticky bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom,0px)+72px)] z-10 md:bottom-24">
          <Button
            block
            size="lg"
            className="shadow-pop"
            disabled={picked.length < 2}
            loading={compare.isPending}
            onClick={() =>
              compare.mutate(picked, { onSuccess: (cmp) => router.push(`/desk/san-hang/so-sanh/${cmp.id}`), onError: notifyError })
            }
          >
            {picked.length < 2 ? "Chọn thêm ít nhất 1 món" : `So sánh ${picked.length} món`}
          </Button>
        </div>
      ) : null}

      <CriteriaSheet
        key={brief.updated_at}
        brief={brief}
        open={edit !== null}
        focus={edit}
        saving={patch.isPending}
        onClose={() => setEdit(null)}
        onSave={(p) => savePatch(p, () => setEdit(null))}
      />
      <LinkSheet open={linkOpen} onClose={() => setLinkOpen(false)} briefId={brief.id} />
    </div>
  );
}
