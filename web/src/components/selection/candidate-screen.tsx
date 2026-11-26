"use client";

import { ArrowRight, ExternalLink, Megaphone, PackageOpen, Stamp, Undo2, X } from "lucide-react";
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
import { useFromCandidate } from "@/lib/api/catalog";
import { PLATFORM_LABELS, STAGE_LABELS, useCandidate, useMoveStage, useUpdateRejection, type ChosenPeer, type Decision, type Stage } from "@/lib/api/selection";
import { SelectionDossier } from "@/components/catalog/desk/selection-dossier";
import { NoteComposer } from "./note-composer";
import { NoteItem } from "./note-item";
import { ReasonsCard } from "./reasons-card";
import { RejectSheet } from "./reject-sheet";
import { RelatedLinks } from "@/components/desk/related-links";
import { SupplierGallery } from "@/components/sourcing/supplier-gallery";

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
  const productId = card.product_id ?? data.decision?.product_id ?? null;

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
      <RelatedLinks
        links={[
          { href: `/desk/san-hang/ung-vien/${card.id}`, label: "Hồ sơ thẩm định" },
          { href: `/desk/nguon-cung/gia-von/${card.id}`, label: "Giá vốn" },
          card.stage === "selected" && productId && { href: `/desk/san-pham/${productId}`, label: "Giá và cách bán (Sản phẩm)" },
        ]}
      />

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="flex gap-3 md:flex-col">
          <ImageBox
            src={card.image_url}
            alt={card.title}
            ratio="4/3"
            placeholder="Chưa có ảnh"
            className="w-32 shrink-0 md:w-full"
            referrerPolicy="no-referrer"
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
          <SupplierGallery candidateId={id} />
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

      {card.stage === "selected" ? <ContentNext candidateId={id} productId={productId} /> : null}
      {data.decision?.decision === "selected" ? <ReasonsCard decision={data.decision} /> : null}
      {card.stage === "selected" && productId ? (
        <section className="flex flex-col gap-3" aria-label="Hồ sơ chọn">
          <SectionLabel aside={<span className="text-[13px] text-ink-3">vì sao chọn, vì sao loại</span>}>Hồ sơ chọn</SectionLabel>
          <SelectionDossier productId={productId} />
        </section>
      ) : null}
      {data.decision?.decision === "rejected" ? <RejectionCard decision={data.decision} /> : null}
      {card.stage === "rejected" ? <ChosenInstead peers={data.chosen_peers ?? []} /> : null}

      <section className="flex flex-col gap-3">
        <SectionLabel aside={<LevelTag level="owner" size="sm" />}>Ghi chú thử · {data.notes.length}</SectionLabel>
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
        label="Đặt cạnh món được chọn trong Hồ sơ chọn"
        description="Hồ sơ chọn của món cùng đề hiện món này (không kèm thương hiệu) cùng vì sao chị loại. Chỉ ở bàn làm việc, không ra website."
        checked={decision.show_on_profile}
        onChange={(v) => update.mutate({ id: decision.id, show_on_profile: v })}
      />
    </Card>
  );
}

/** Món đã chọn → bước tiếp: làm nội dung cho mọi kênh bán (Website trước, rồi mạng xã hội). */
function ContentNext({ candidateId, productId }: { candidateId: string; productId: string | null }) {
  const create = useFromCandidate();
  return (
    <Card tone="accent" className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-semibold">Bước tiếp: làm nội dung các kênh</p>
        <p className="text-[13.5px] text-ink-2">
          {productId
            ? "Trang website trước (AI đã viết nháp từ hồ sơ này), chị đăng rồi AI soạn bài Facebook, Instagram, Threads, TikTok, Zalo."
            : "Chưa có sản phẩm nháp cho món này nên chưa làm nội dung được. Thường hệ thống tạo ngay khi đóng dấu; chị tạo tay ở đây."}
        </p>
      </div>
      {productId ? (
        <ButtonLink href={`/desk/noi-dung/san-pham/${productId}`} icon={<Megaphone className="size-4" aria-hidden />} className="self-start sm:self-center">
          Làm nội dung các kênh
        </ButtonLink>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button disabled icon={<Megaphone className="size-4" aria-hidden />}>
            Làm nội dung các kênh
          </Button>
          <Button variant="secondary" loading={create.isPending} onClick={() => create.mutate(candidateId, { onSuccess: () => notifySuccess("Đã tạo sản phẩm nháp") })}>
            Tạo sản phẩm nháp
          </Button>
        </div>
      )}
    </Card>
  );
}

/** Món bị loại: món đã chọn cùng đề (nếu có) — hồ sơ chọn của món đó đặt các món đã loại cạnh nó. */
function ChosenInstead({ peers }: { peers: ChosenPeer[] }) {
  if (!peers.length) return null;
  return (
    <section className="flex flex-col gap-2" aria-label="Món được chọn thay">
      <SectionLabel>Cùng đề, chị đã chọn</SectionLabel>
      <ul className="flex flex-col gap-2">
        {peers.map((p) => (
          <li key={p.candidate_id}>
            <Link
              href={`/desk/ban-chon/${p.candidate_id}`}
              className="flex items-center gap-3 rounded-md border border-line bg-surface p-3 transition-colors hover:border-line-strong"
            >
              <Seal size={40} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-semibold">{p.title}</span>
                <span className="block text-[13px] text-ink-2">Xem hồ sơ chọn: món này đặt cạnh các món đã loại, kèm lý do</span>
              </span>
              <ArrowRight className="size-4 shrink-0 text-ink-3" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
