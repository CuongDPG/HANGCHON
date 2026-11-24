"use client";

import { MessageCircleQuestion, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, DateTime, EmptyState, SectionLabel, SkeletonList, notifyError } from "@/components/ui";
import { useDemand, useDemandBrief, useDemandDigest, useDismissDemand, useRun, type Demand } from "@/lib/api/sourcing";
import { RunProgress } from "./run-progress";

const SOURCE: Record<string, string> = {
  message: "tin nhắn",
  comment: "bình luận",
  find_request: "Nhờ chị tìm",
  assistant: "trợ lý web",
  manual: "ghi tay",
};

function DemandItem({ d }: { d: Demand }) {
  const router = useRouter();
  const open = useDemandBrief();
  const dismiss = useDismissDemand();
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-start gap-3">
        <div className="grid size-12 shrink-0 place-items-center rounded-md bg-accent-wash text-accent">
          <span className="font-display text-xl leading-none font-bold tabular-nums">{d.ask_count}</span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold first-letter:uppercase">{d.title}</p>
          <p className="text-[13px] text-ink-2">
            {d.ask_count} người hỏi · {d.mention_count} lần nhắc
            {d.last_asked_at ? (
              <>
                {" "}
                · <DateTime value={d.last_asked_at} format="relative" />
              </>
            ) : null}
          </p>
        </div>
        {d.status === "searching" ? <Badge tone="accent">Đang tìm</Badge> : null}
      </div>
      <ul className="flex flex-col gap-1 border-l-2 border-line pl-3">
        {d.mentions.slice(0, 2).map((m) => (
          <li key={m.id} className="text-[13px] text-ink-2">
            «{m.text}» <span className="text-ink-3">— {SOURCE[m.source] ?? m.source}</span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        {d.brief_id ? (
          <Button size="sm" variant="secondary" onClick={() => router.push(`/desk/san-hang/de/${d.brief_id}`)}>
            Xem đề tìm
          </Button>
        ) : (
          <Button
            size="sm"
            loading={open.isPending}
            onClick={() => open.mutate(d.id, { onSuccess: (b) => router.push(`/desk/san-hang/de/${b.id}`), onError: notifyError })}
          >
            Mở đề tìm
          </Button>
        )}
        <Button size="sm" variant="ghost" loading={dismiss.isPending} onClick={() => dismiss.mutate(d.id)}>
          Bỏ qua
        </Button>
      </div>
    </Card>
  );
}

/** a6 — Nghe khách muốn gì: câu hỏi, lời nhờ tìm gom thành nhu cầu, xếp theo số người hỏi. */
export function DemandPanel() {
  const qc = useQueryClient();
  const { data, isPending, error } = useDemand();
  const digest = useDemandDigest();
  const [runId, setRunId] = useState<string | null>(null);
  const run = useRun(runId);
  useEffect(() => {
    if (run.data && run.data.status !== "queued" && run.data.status !== "running") qc.invalidateQueries({ queryKey: ["sourcing", "demand"] });
  }, [run.data, qc]);

  return (
    <section className="flex flex-col gap-3" aria-label="Khách muốn gì">
      <SectionLabel
        aside={
          <Button
            size="sm"
            variant="ghost"
            icon={<RefreshCw className="size-4" />}
            loading={digest.isPending}
            onClick={() => digest.mutate(undefined, { onSuccess: (r) => setRunId(r.id), onError: notifyError })}
          >
            Gom lại
          </Button>
        }
      >
        Khách đang hỏi
      </SectionLabel>
      <p className="-mt-1 text-[13px] text-ink-2">Từ tin nhắn, bình luận và trang Nhờ chị tìm. Xếp theo số người hỏi.</p>
      {run.data ? <RunProgress run={run.data} /> : null}
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được nhu cầu khách" description={error.message} />
      ) : !data.items.length ? (
        <EmptyState icon={<MessageCircleQuestion />} title="Chưa có khách nào hỏi tìm món" description="Khi khách nhắn hỏi một món, AI sẽ gom vào đây." />
      ) : (
        data.items.map((d) => <DemandItem key={d.id} d={d} />)
      )}
    </section>
  );
}
