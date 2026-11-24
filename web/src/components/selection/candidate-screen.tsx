"use client";

import { ArrowRight, ExternalLink, PackageOpen, Stamp, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  DataList,
  DateTime,
  EmptyState,
  ImageBox,
  LevelTag,
  Money,
  PageHeader,
  ProgressBar,
  Seal,
  SectionLabel,
  SkeletonList,
  Switch,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import type { DataListItem } from "@/components/ui";
import { PLATFORM_LABELS, STAGE_LABELS, useCandidate, useMoveStage, useUpdateRejection, type Decision, type Stage } from "@/lib/api/selection";
import { NoteComposer } from "./note-composer";
import { NoteItem } from "./note-item";
import { ReasonsCard } from "./reasons-card";
import { RejectSheet } from "./reject-sheet";

/** Một món trên bàn chọn: thông tin nguồn, nhật ký thử (c2), lý do chọn (c3) / loại (c4), chuyển cột (c1). */
export function CandidateScreen({ id }: { id: string }) {
  const { data, isPending, error } = useCandidate(id);
  const move = useMoveStage();
  const confirm = useConfirm();
  const [rejecting, setRejecting] = useState(false);

  if (isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Đang tải…" backHref="/desk/ban-chon" />
        <SkeletonList rows={3} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Không mở được món này" backHref="/desk/ban-chon" />
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      </div>
    );
  }

  const { card } = data;

  async function go(to: Stage) {
    if (to === "rejected") {
      setRejecting(true);
      return;
    }
    if (card.stage === "selected" || card.stage === "rejected") {
      const ok = await confirm({
        title: `Đưa về «${STAGE_LABELS[to]}»?`,
        message: "Quyết định cũ vẫn được giữ trong lịch sử. Bản nháp lý do đang chờ duyệt sẽ bị huỷ.",
        confirmLabel: "Đổi ý",
      });
      if (!ok) return;
    }
    await move.mutateAsync({ id, to });
    notifySuccess(to === "selected" ? "Đã đóng dấu chọn. AI soạn lý do từ ghi chú, chị sửa lời rồi chốt." : `Đã chuyển sang ${STAGE_LABELS[to]}`);
  }

  const facts: (DataListItem | null)[] = [
    data.price_amount ? { label: "Giá ở nguồn", value: `${Number(data.price_amount).toLocaleString("vi-VN")} ${data.price_currency ?? ""}` } : null,
    card.price_vnd_estimate ? { label: "Quy đổi nhanh", value: <Money value={card.price_vnd_estimate} /> } : null,
    data.weight_grams ? { label: "Cân nặng", value: `${(data.weight_grams / 1000).toLocaleString("vi-VN")} kg` } : null,
    {
      label: "Giá vốn về tay",
      value: card.landed_cost_vnd ? (
        <Link href={`/desk/nguon-cung/gia-von/${id}`} className="font-semibold text-accent hover:underline">
          <Money value={card.landed_cost_vnd} />
        </Link>
      ) : (
        <Link href={`/desk/nguon-cung/gia-von/${id}`} className="text-accent hover:underline">
          Tính giá vốn
        </Link>
      ),
    },
    card.ai_score !== null ? { label: "Điểm AI", value: `${card.ai_score}/100` } : null,
  ];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={card.title}
        eyebrow={`${STAGE_LABELS[card.stage].toUpperCase()} · ${PLATFORM_LABELS[card.source_platform] ?? card.source_platform}`}
        backHref={`/desk/ban-chon?tab=${card.stage}`}
      />

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="flex gap-3 md:flex-col">
          <ImageBox
            src={card.image_url}
            alt={card.title}
            ratio="4/3"
            placeholder="Chưa có ảnh"
            className="w-32 shrink-0 md:w-full"
            overlay={card.stage === "selected" ? <Seal chosen={card.seal?.chosen} total={card.seal?.total} size={56} /> : null}
          />
          <div className="flex min-w-0 flex-col gap-2">
            {data.title_original ? <p className="text-[13px] text-ink-2">Tên gốc: {data.title_original}</p> : null}
            {data.source_url ? (
              <a href={data.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[14px] text-accent hover:underline">
                Mở trang nguồn <ExternalLink className="size-3.5" aria-hidden />
              </a>
            ) : null}
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <Card>
            <DataList items={facts.filter((x): x is DataListItem => x !== null)} />
          </Card>
          {card.stage === "trial" && card.trial_day !== null ? (
            <Card tone="accent">
              <p className="mb-2 text-[15px]">
                Ngày thử thứ <span className="font-display text-xl font-bold tabular-nums">{card.trial_day}</span> trong {card.trial_days}
              </p>
              <ProgressBar value={Math.min(card.trial_day, card.trial_days)} max={card.trial_days} label={`Ngày thử thứ ${card.trial_day} trong ${card.trial_days}`} />
            </Card>
          ) : null}
          <StageActions stage={card.stage} busy={move.isPending} onGo={go} candidateId={id} />
        </div>
      </div>

      {data.decision?.decision === "selected" ? <ReasonsCard decision={data.decision} /> : null}
      {data.decision?.decision === "rejected" ? <RejectionCard decision={data.decision} /> : null}

      <section className="flex flex-col gap-3">
        <SectionLabel aside={<LevelTag level="owner" size="sm" />}>Ghi chú của chị · {data.notes.length}</SectionLabel>
        <NoteComposer candidateId={id} />
        {data.notes.length ? (
          <ul className="flex flex-col gap-2">
            {data.notes.map((n) => (
              <NoteItem key={n.id} note={n} />
            ))}
          </ul>
        ) : (
          <p className="text-[14px] text-ink-2">Chưa có ghi chú. Trong lúc dùng, chị nói vài câu; AI sắp thành ý gọn: điểm tốt, chưa ưng, số đo.</p>
        )}
      </section>

      {data.history.length > 1 ? (
        <section className="flex flex-col gap-2">
          <SectionLabel>Lịch sử quyết định</SectionLabel>
          <ul className="flex flex-col gap-1 text-[14px] text-ink-2">
            {data.history.map((d) => (
              <li key={d.id}>
                <DateTime value={d.decided_at} format="date" /> · {d.decision === "selected" ? "Chọn" : `Loại: ${d.rejection_reason ?? ""}`}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <RejectSheet candidate={rejecting ? { id, title: card.title } : null} onClose={() => setRejecting(false)} />
    </div>
  );
}

function StageActions({ stage, busy, onGo, candidateId }: { stage: Stage; busy: boolean; onGo: (s: Stage) => void; candidateId: string }) {
  const btn = (to: Stage, label: string, variant: "primary" | "secondary" | "danger" = "secondary", icon?: ReactNode) => (
    <Button key={to} variant={variant} disabled={busy} onClick={() => onGo(to)} icon={icon}>
      {label}
    </Button>
  );
  const reject = btn("rejected", "Loại, ghi lý do", "secondary", <X className="size-4" aria-hidden />);
  const actions: Record<Stage, ReactNode[]> = {
    candidate: [
      btn("sample", "Mua mẫu", "secondary", <PackageOpen className="size-4" aria-hidden />),
      btn("trial", "Bắt đầu thử", "primary", <ArrowRight className="size-4" aria-hidden />),
      reject,
    ],
    sample: [btn("trial", "Mẫu về, bắt đầu thử", "primary", <ArrowRight className="size-4" aria-hidden />), reject],
    trial: [reject, btn("selected", "Đóng dấu Đã chọn", "primary", <Stamp className="size-4" aria-hidden />)],
    selected: [btn("trial", "Đổi ý: thử thêm", "secondary", <Undo2 className="size-4" aria-hidden />)],
    rejected: [btn("candidate", "Xem lại: về Ứng viên", "secondary", <Undo2 className="size-4" aria-hidden />)],
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2 max-md:[&>button]:flex-1">{actions[stage]}</div>
      {stage === "sample" ? (
        <ButtonLink href={`/desk/nguon-cung?tab=don&candidate=${candidateId}`} variant="ghost" size="sm" className="self-start">
          Xem đơn đặt mẫu
        </ButtonLink>
      ) : null}
    </div>
  );
}

function RejectionCard({ decision }: { decision: Decision }) {
  const update = useUpdateRejection();
  return (
    <Card tone="danger" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <LevelTag level="owner">Lý do loại</LevelTag>
        <span className="text-[13px] text-ink-2">
          <DateTime value={decision.decided_at} format="date" />
        </span>
      </div>
      <p className="text-[15px]">{decision.rejection_reason}</p>
      <div className="flex flex-wrap gap-1.5">
        {decision.rejection_groups.map((g) => (
          <Badge key={g.key} tone="danger">
            {g.label}
          </Badge>
        ))}
      </div>
      <Switch
        label="Hiện ở trang Hồ sơ chọn"
        description="Khách thấy món này đã bị loại và vì sao."
        checked={decision.show_on_profile}
        onChange={(v) => update.mutate({ id: decision.id, show_on_profile: v })}
      />
    </Card>
  );
}
