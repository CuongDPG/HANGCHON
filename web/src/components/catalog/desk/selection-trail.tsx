"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card, SectionLabel } from "@/components/ui/card";
import { DataList } from "@/components/ui/data-display";
import { DateTime } from "@/components/ui/date-time";
import { EmptyState, ScoreBar, SkeletonList } from "@/components/ui/feedback";
import { Money } from "@/components/ui/money";
import { useSelectionTrail, type SelectionTrail } from "@/lib/api/catalog";
import { formatNumber } from "@/lib/format";
import { SupplierGallery } from "@/components/sourcing/supplier-gallery";
import { SelectionDossier } from "./selection-dossier";

const SAFETY_TONE: Record<NonNullable<SelectionTrail["assessment"]>["safety_status"], BadgeTone> = {
  ok: "success",
  warning: "warning",
  blocked: "danger",
  unchecked: "outline",
};

/**
 * Tab «Hồ sơ chọn»: lần ngược quá trình chọn của một món. Trên cùng là hồ sơ so sánh (dải số sàng lọc, món đã loại),
 * dưới là dấu vết từng bước — đề săn hàng, thẩm định, mua mẫu và thử, quyết định, giá vốn. Chỉ đọc: mỗi bước có link
 * sang đúng trang để sửa.
 */
export function SelectionTrailView({ productId }: { productId: string }) {
  const { data: t, isPending, error } = useSelectionTrail(productId);

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3" aria-label="Chọn giữa các mẫu">
        <SectionLabel aside={t?.candidate_id ? <StepLink href={`/desk/ban-chon/${t.candidate_id}`}>Bàn chọn</StepLink> : null}>
          So với các mẫu khác
        </SectionLabel>
        <SelectionDossier productId={productId} />
      </section>

      {t?.candidate_id ? <SupplierGallery candidateId={t.candidate_id} /> : null}

      <section className="flex flex-col gap-3" aria-label="Dấu vết từng bước">
        <SectionLabel>Dấu vết từng bước</SectionLabel>
        {isPending ? (
          <SkeletonList rows={4} />
        ) : error || !t ? (
          <EmptyState tone="error" title="Chưa tải được dấu vết chọn" description={error?.message} />
        ) : !t.candidate_id ? (
          <EmptyState title="Món này không đi qua Săn hàng" description="Sản phẩm được thêm thẳng, nên không có đề, hồ sơ thẩm định hay ghi chú thử." />
        ) : (
          <ol className="grid gap-3 lg:grid-cols-2">
            <HuntStep t={t} />
            <AssessmentStep t={t} />
            <TrialStep t={t} />
            <DecisionStep t={t} />
            <CostStep t={t} />
          </ol>
        )}
      </section>
    </div>
  );
}

function StepLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-[14px] font-semibold whitespace-nowrap text-accent">
      {children} →
    </Link>
  );
}

function Step({ n, title, link, children }: { n: number; title: string; link?: ReactNode; children: ReactNode }) {
  return (
    <li className="min-w-0">
      <Card className="flex h-full flex-col gap-3 border border-line">
        <div className="flex items-start justify-between gap-3">
          <h3 className="flex items-center gap-2 text-[15px] font-semibold">
            <span aria-hidden className="inline-grid size-6 place-items-center rounded-sm bg-accent-wash font-display text-[13px] text-accent">
              {n}
            </span>
            {title}
          </h3>
          {link}
        </div>
        {children}
      </Card>
    </li>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-[14px] text-ink-2">{children}</p>;
}

function HuntStep({ t }: { t: SelectionTrail }) {
  const h = t.hunt!;
  return (
    <Step
      n={1}
      title="Săn hàng"
      link={<StepLink href={h.brief_id ? `/desk/san-hang/de/${h.brief_id}` : `/desk/san-hang/ung-vien/${t.candidate_id}`}>{h.brief_id ? "Đề săn hàng" : "Ứng viên"}</StepLink>}
    >
      {h.brief_title ? (
        <div>
          <p className="text-[15px] font-semibold">{h.brief_title}</p>
          {h.brief_text && h.brief_text !== h.brief_title ? <p className="mt-0.5 text-[14px] text-ink-2">«{h.brief_text}»</p> : null}
        </div>
      ) : (
        <Muted>Không theo đề nào.</Muted>
      )}
      <DataList
        items={[
          { label: "Tìm thấy", value: <span>{h.origin} · <DateTime value={h.found_at} /></span> },
          { label: "Nguồn", value: h.source_url ? <a href={h.source_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{h.platform}{h.seller_name ? ` · ${h.seller_name}` : ""}</a> : h.platform },
          ...(h.source_price_vnd ? [{ label: "Giá ở nguồn (quy đổi)", value: <Money value={h.source_price_vnd} /> }] : []),
          ...(h.source_rating ? [{ label: "Điểm ở nguồn", value: `${h.source_rating.toLocaleString("vi-VN")}★${h.source_review_count ? ` · ${formatNumber(h.source_review_count)} đánh giá` : ""}` }] : []),
          ...(h.price_max_vnd ? [{ label: "Đề đặt giá bán tối đa", value: <Money value={h.price_max_vnd} /> }] : []),
        ]}
      />
    </Step>
  );
}

function AssessmentStep({ t }: { t: SelectionTrail }) {
  const a = t.assessment;
  return (
    <Step n={2} title="Thẩm định" link={<StepLink href={`/desk/san-hang/ung-vien/${t.candidate_id}`}>Hồ sơ thẩm định</StepLink>}>
      {!a ? (
        <Muted>Chưa có hồ sơ thẩm định.</Muted>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {a.score_total !== null ? (
              <span className="font-display text-[22px] leading-none font-extrabold tabular-nums">
                {Math.round(a.score_total)}
                <span className="text-[14px] font-normal text-ink-3">/100</span>
              </span>
            ) : null}
            <Badge tone={a.score_confirmed ? "success" : "outline"}>{a.score_confirmed ? "Chị đã duyệt điểm" : "Điểm AI chấm nháp"}</Badge>
            <Badge tone={SAFETY_TONE[a.safety_status]}>An toàn: {a.safety_label}</Badge>
            {a.ai_score !== null ? <span className="text-[13px] text-ink-2">Khớp đề + gu: {a.ai_score}</span> : null}
          </div>
          {a.summary ? <p className="text-[14px]">{a.summary}</p> : null}
          {a.scores.length ? (
            <div className="flex flex-col gap-1.5">
              {a.scores.map((s) => (s.score === null ? null : <ScoreBar key={s.label} label={s.label} score={s.score} max={10} />))}
            </div>
          ) : null}
          {a.strengths.length || a.weaknesses.length ? (
            <ul className="flex flex-col gap-1 text-[14px]">
              {a.strengths.map((s) => (
                <li key={`+${s}`}>
                  <span className="font-semibold text-auto">+</span> {s}
                </li>
              ))}
              {a.weaknesses.map((s) => (
                <li key={`-${s}`}>
                  <span className="font-semibold text-seal">−</span> {s}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-[13px] text-ink-2">
            Nguy cơ hàng nhái: {a.counterfeit_risk} · đánh giá ảo: {a.fake_review_risk}
            {a.safety_notes ? ` · ${a.safety_notes}` : ""}
          </p>
        </>
      )}
    </Step>
  );
}

function TrialStep({ t }: { t: SelectionTrail }) {
  const tr = t.trial;
  return (
    <Step n={3} title="Mua mẫu và dùng thử" link={<StepLink href={`/desk/ban-chon/${t.candidate_id}`}>Nhật ký thử</StepLink>}>
      {t.samples.length ? (
        <ul className="flex flex-col gap-1.5">
          {t.samples.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 text-[14px]">
              <Link href={`/desk/nguon-cung/don/${s.id}`} className="font-semibold text-accent hover:underline">
                Đơn mẫu {s.code}
              </Link>
              <span className="flex items-center gap-2 text-ink-2">
                {s.total_vnd ? <Money value={s.total_vnd} /> : null}
                {s.received_at ? <span>nhận <DateTime value={s.received_at} format="dayMonth" /></span> : null}
                <Badge tone={s.status === "received" ? "success" : "neutral"}>{s.status_label}</Badge>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Muted>Không có đơn đặt mẫu (mẫu có sẵn hoặc chị tự mua).</Muted>
      )}
      {tr ? (
        <>
          <p className="text-[14px]">
            {tr.trial_days ? <span className="font-semibold">Chị dùng thử {tr.trial_days} ngày</span> : <span className="font-semibold">Đang thử</span>}
            {tr.started_at ? (
              <span className="text-ink-2">
                {" "}
                · <DateTime value={tr.started_at} format="dayMonth" />
                {tr.ended_at ? <> – <DateTime value={tr.ended_at} format="dayMonth" /></> : null}
              </span>
            ) : null}
            <span className="text-ink-2">
              {" "}
              · {tr.note_count} ghi chú{tr.tester_count ? ` · ${tr.tester_count} khách thử cùng` : ""}
            </span>
          </p>
          {tr.notes.length ? (
            <ul className="flex flex-col gap-2">
              {tr.notes.map((n, i) => (
                <li key={i} className="rounded-md bg-soft px-3 py-2 text-[14px]">
                  <p className="line-clamp-3">{n.text}</p>
                  <p className="mt-0.5 text-[12.5px] text-ink-3">
                    {n.trial_day ? `Ngày ${n.trial_day} · ` : ""}
                    <DateTime value={n.recorded_at} format="dayMonth" />
                    {n.author ? ` · ${n.author}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : (
        <Muted>Chưa có ghi chú thử.</Muted>
      )}
    </Step>
  );
}

function DecisionStep({ t }: { t: SelectionTrail }) {
  const d = t.decision;
  return (
    <Step n={4} title="Quyết định chọn" link={<StepLink href={`/desk/ban-chon/${t.candidate_id}`}>Sửa lời ở Bàn chọn</StepLink>}>
      {!d ? (
        <Muted>Chưa có quyết định chọn.</Muted>
      ) : (
        <>
          <p className="text-[13px] text-ink-2">
            {d.decided_by ? `${d.decided_by} chọn` : "Chọn"} lúc <DateTime value={d.decided_at} format="dateTime" />
            {d.wording_pending ? " · lời AI soạn đang chờ chị sửa" : ""}
          </p>
          <div>
            <p className="text-[13px] font-semibold text-ink-2">Vì sao chọn</p>
            {d.reason_selected ? (
              <ul className="mt-1 flex list-disc flex-col gap-0.5 pl-5 text-[15px]">
                {d.reason_selected.split("\n").filter(Boolean).map((line) => (
                  <li key={line}>{line.replace(/^[-•]\s*/, "")}</li>
                ))}
              </ul>
            ) : (
              <Muted>Chưa có lời.</Muted>
            )}
          </div>
          <div>
            <p className="text-[13px] font-semibold text-ink-2">Điều chưa ưng</p>
            <p className="mt-1 text-[15px]">{d.not_satisfied || <span className="text-ink-2">Chưa ghi.</span>}</p>
          </div>
        </>
      )}
    </Step>
  );
}

function CostStep({ t }: { t: SelectionTrail }) {
  const c = t.cost;
  return (
    <Step n={5} title="Giá vốn và giá bán" link={<StepLink href={`/desk/nguon-cung/gia-von/${t.candidate_id}`}>Bảng giá vốn</StepLink>}>
      {c.landed_cost_vnd === null ? (
        <Muted>Chưa tính giá vốn về tay.</Muted>
      ) : (
        <DataList
          items={[
            ...c.breakdown.map((b) => ({ label: b.label, value: <Money value={b.amount_vnd} /> })),
            { label: "Giá vốn về tay (1 cái)", value: <Money value={c.landed_cost_vnd} />, strong: true },
          ]}
        />
      )}
      <DataList
        items={[
          ...(c.proposed_price_vnd ? [{ label: "AI đề xuất giá", value: <Money value={c.proposed_price_vnd} /> }] : []),
          { label: c.approved_at ? "Giá bán chị duyệt" : "Giá bán", value: c.price_vnd ? <Money value={c.price_vnd} /> : <span className="text-seal">Chưa có giá</span> },
          ...(c.margin_pct !== null ? [{ label: "Biên lãi gộp", value: `${c.margin_pct.toLocaleString("vi-VN")}%` }] : []),
        ]}
      />
    </Step>
  );
}
