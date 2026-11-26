"use client";

import { ExternalLink, FileSearch, RotateCw, Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  IconButton,
  ImageBox,
  LevelTag,
  PageHeader,
  Skeleton,
  SkeletonList,
  Spinner,
  notifyError,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { useProfile, useRunAssessment } from "@/lib/api/assessment";
import { platformLabel } from "@/lib/api/sourcing";
import { formatNumber } from "@/lib/format";
import { STAGE_LABEL } from "@/components/sourcing/candidate-row";
import { GuidanceNotes } from "@/components/sourcing/guidance-notes";
import { CostCard } from "./cost-card";
import { DecisionBar } from "./decision-bar";
import { ReviewsCard } from "./reviews-card";
import { ScoreCard } from "./score-card";
import { WarningsCard } from "./warnings-card";
import { RelatedLinks } from "@/components/desk/related-links";
import { SupplierGallery } from "@/components/sourcing/supplier-gallery";

const STEP_LABEL: Record<string, string> = {
  details: "lấy chi tiết",
  reviews: "đọc đánh giá",
  market: "tìm giá ở Việt Nam",
  safety: "soát an toàn",
  risk: "soát hàng nhái",
  score: "chấm điểm",
};

/** b1 — Hồ sơ thẩm định: một trang đủ để chị quyết loại, mua mẫu hay chọn. */
export function ProfileScreen({ id }: { id: string }) {
  const params = useSearchParams();
  const { data, isPending, error, refetch } = useProfile(id);
  const run = useRunAssessment(id);
  const session = useSession();
  const canEdit = session.user?.role === "owner";
  const autoStarted = useRef(false);

  const a = data?.assessment ?? null;
  const assessing = !!a && (a.status === "pending" || a.status === "running");

  // Dán link xong (?tham-dinh=1) thì tự thẩm định một lần nếu chưa có hồ sơ.
  useEffect(() => {
    if (!data || autoStarted.current || params.get("tham-dinh") !== "1" || data.assessment) return;
    autoStarted.current = true;
    run.mutate(undefined, { onError: notifyError });
  }, [data, params, run]);

  if (isPending)
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Đang tải">
        <Skeleton className="h-8 w-60" />
        <Skeleton className="h-24 w-full" />
        <SkeletonList rows={4} />
      </div>
    );
  if (error || !data)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Hồ sơ thẩm định" backHref="/desk/san-hang" />
        <EmptyState
          tone="error"
          title="Chưa tải được hồ sơ"
          description={error?.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      </div>
    );

  const c = data.candidate;
  const back = data.brief ? `/desk/san-hang/de/${data.brief.id}` : "/desk/san-hang";
  const total = a?.score_total ? Math.round(Number(a.score_total)) : null;
  const start = () => run.mutate(undefined, { onError: notifyError });

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        backHref={back}
        eyebrow={data.brief ? `${data.brief.title} · ${data.brief.considered_count} ứng viên` : "Ứng viên"}
        title={c.title_vi}
        actions={
          a && !assessing ? (
            <IconButton label="Thẩm định lại" icon={<RotateCw />} onClick={start} disabled={run.isPending} />
          ) : undefined
        }
      />
      <RelatedLinks links={[{ href: `/desk/ban-chon/${c.id}`, label: "Trên bàn chọn" }, { href: `/desk/nguon-cung/gia-von/${c.id}`, label: "Giá vốn" }]} />

      <div className="flex items-start gap-3">
        <ImageBox src={c.thumb_url} alt={c.title_vi} className="w-[84px] shrink-0" placeholder="" priority referrerPolicy="no-referrer" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[34px] leading-none font-bold tabular-nums">{total ?? c.ai_score ?? "—"}</span>
            <span className="text-ink-3">/100</span>
          </div>
          <p className="mt-1 text-[13px] text-ink-2">
            {total !== null
              ? a?.score_status === "confirmed"
                ? "Chị đã duyệt điểm"
                : "AI chấm nháp, chị sửa được từng dòng"
              : "Điểm khớp đề lúc tìm, chưa thẩm định"}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[13px] text-ink-2">
            <span>{platformLabel(c.source_platform)}</span>
            {c.seller_name ? <span>· {c.seller_name}</span> : null}
            {c.review_count ? <span>· {formatNumber(c.review_count)} đánh giá</span> : null}
            {c.source_url ? (
              <a href={c.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent">
                <ExternalLink className="size-3" aria-hidden /> Nguồn
              </a>
            ) : null}
          </p>
          {c.stage !== "candidate" ? (
            <Badge tone="accent" className="mt-1">
              {STAGE_LABEL[c.stage]}
            </Badge>
          ) : null}
        </div>
      </div>

      <SupplierGallery candidateId={c.id} />

      {c.guidance ? (
        <Card className="flex flex-col gap-2">
          <CardHeader title="Nguyên tắc và gu của chị" />
          <GuidanceNotes g={c.guidance} />
        </Card>
      ) : null}

      {assessing ? (
        <Card tone="soft" className="flex items-center gap-3" role="status">
          <Spinner className="size-5" />
          <p className="text-sm">
            AI đang thẩm định: {(a?.pending_steps?.length ? a.pending_steps : Object.keys(STEP_LABEL)).map((s) => STEP_LABEL[s] ?? s).join(", ")}…
          </p>
        </Card>
      ) : null}
      {a?.error ? <p className="text-[13px] text-review">Có bước chưa xong: {a.error}</p> : null}

      {!a ? (
        <EmptyState
          icon={<FileSearch />}
          title="Chưa có hồ sơ thẩm định"
          description="AI sẽ đọc đánh giá, tìm giá ở Việt Nam, soát an toàn và chấm nháp theo khung của chị."
          action={
            <Button icon={<Sparkles className="size-4" />} loading={run.isPending} onClick={start}>
              Thẩm định món này
            </Button>
          }
        />
      ) : null}

      {a && a.scores.length ? <ScoreCard a={a} candidateId={id} canEdit={canEdit} /> : null}

      {a?.summary ? (
        <Card className="flex flex-col gap-2">
          <CardHeader title="Tóm tắt" aside={<LevelTag level="auto" size="sm" />} />
          <p className="text-[15px] [text-wrap:pretty]">{a.summary}</p>
          {a.strengths.length ? (
            <ul className="flex list-disc flex-col gap-0.5 pl-5 text-sm">
              {a.strengths.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : null}
          {a.weaknesses.length ? (
            <ul className="flex list-disc flex-col gap-0.5 pl-5 text-sm text-ink-2 marker:text-seal">
              {a.weaknesses.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : null}

      {data.review_digest ? <ReviewsCard d={data.review_digest} total={c.review_count} /> : null}
      <CostCard cost={data.cost} market={data.market} />
      {a || data.warnings.length ? <WarningsCard warnings={data.warnings} a={a} candidateId={id} canEdit={canEdit} /> : null}

      {Object.keys(a?.specs ?? c.specs ?? {}).length ? (
        <Card>
          <CardHeader title="Thông số (đã dịch)" />
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            {Object.entries(a?.specs && Object.keys(a.specs).length ? a.specs : c.specs).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-2">{k}</dt>
                <dd>{String(v)}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : null}

      <DecisionBar candidateId={id} title={c.title_vi} stage={c.stage} />
    </div>
  );
}
