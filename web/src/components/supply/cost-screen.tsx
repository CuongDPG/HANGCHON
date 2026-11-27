"use client";

import { DeskMoreMenu } from "@/components/desk/desk-more-menu";
import { relatedItems } from "@/components/desk/related-links";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Check, Sparkles, X } from "lucide-react";
import { useDeferredValue, useState } from "react";
import {
  Badge,
  Button,
  Card,
  DataList,
  DateTime,
  EmptyState,
  Input,
  LevelTag,
  Money,
  PageHeader,
  SectionLabel,
  Segmented,
  SkeletonList,
  Switch,
  Textarea,
  notifySuccess,
} from "@/components/ui";
import { formatVnd } from "@/lib/format";
import { useSession } from "@/lib/api/auth";
import { useCandidate, type CandidateDetail } from "@/lib/api/selection";
import {
  num,
  previewCost,
  useApproveItem,
  useCostParams,
  useCurrentSheet,
  usePriceProposals,
  useProposePrice,
  useReturnItem,
  useSaveCostSheet,
  type CostInput,
  type CostSheet,
  type PriceProposal,
} from "@/lib/api/supply";

/** Giá vốn về tay (d2) + đề xuất giá bán (d3) của một ứng viên. */
export function CostScreen({ candidateId }: { candidateId: string }) {
  const cand = useCandidate(candidateId);
  const sheet = useCurrentSheet(candidateId);
  if (cand.isPending || sheet.isPending)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader loading backHref="/desk/nguon-cung?tab=gia-von" />
        <SkeletonList rows={3} />
      </div>
    );
  if (cand.error || sheet.error)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Giá vốn về tay" backHref="/desk/nguon-cung?tab=gia-von" />
        <EmptyState tone="error" title="Chưa tải được" description={(cand.error ?? sheet.error)?.message} />
      </div>
    );
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Giá vốn về tay"
        eyebrow={cand.data.card.title}
        backHref="/desk/nguon-cung?tab=gia-von"
        actions={<DeskMoreMenu items={relatedItems([{ href: `/desk/ban-chon/${candidateId}`, label: "Trên bàn chọn" }])} />}
      />
      <CostForm key={sheet.data?.id ?? "new"} cand={cand.data} sheet={sheet.data ?? null} />
      <PriceSection candidateId={candidateId} hasSheet={!!sheet.data} />
    </div>
  );
}

function CostForm({ cand, sheet }: { cand: CandidateDetail; sheet: CostSheet | null }) {
  const params = useCostParams();
  const save = useSaveCostSheet();
  const [f, setF] = useState(() => ({
    unit_price_amount: String(sheet?.unit_price_amount ?? cand.price_amount ?? ""),
    currency: sheet?.currency ?? cand.price_currency ?? "CNY",
    weight_grams: String(sheet?.weight_grams ?? cand.weight_grams ?? ""),
    domestic_shipping_vnd: sheet ? String(sheet.domestic_shipping_vnd) : "",
    packaging_vnd: sheet ? String(sheet.packaging_vnd) : "",
    other_fees_vnd: String(sheet?.other_fees_vnd ?? 0),
    auto_update: sheet?.auto_update ?? true,
    fx_rate: sheet && !sheet.auto_update ? String(sheet.fx_rate) : "",
    vat_pct: "",
  }));
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const intOrNull = (v: string) => (v.trim() === "" ? null : Math.max(0, Math.round(Number(v))));
  const body: CostInput = {
    candidate_id: cand.card.id,
    supplier_id: cand.supplier_id,
    unit_price_amount: f.unit_price_amount || "0",
    currency: f.currency,
    weight_grams: intOrNull(f.weight_grams),
    domestic_shipping_vnd: intOrNull(f.domestic_shipping_vnd),
    packaging_vnd: intOrNull(f.packaging_vnd),
    other_fees_vnd: intOrNull(f.other_fees_vnd) ?? 0,
    auto_update: f.auto_update,
    fx_rate: !f.auto_update && f.fx_rate ? f.fx_rate : null,
    vat_pct: !f.auto_update && f.vat_pct ? f.vat_pct : null,
  };
  const deferred = useDeferredValue(body);
  const valid = Number(f.unit_price_amount) > 0;
  const preview = useQuery({
    queryKey: ["supply", "preview", deferred],
    queryFn: () => previewCost(deferred),
    enabled: valid,
    placeholderData: keepPreviousData,
    meta: { silentError: true },
  });
  const p = params.data;
  const fxDefault = p?.fx_rates[f.currency];

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <SectionLabel>Đầu vào</SectionLabel>
          <LevelTag level="auto" size="sm" />
        </div>
        <Segmented
          aria-label="Tiền tệ"
          value={f.currency}
          onChange={(v) => setF((x) => ({ ...x, currency: v }))}
          block
          options={["CNY", "JPY", "USD"].map((c) => ({ value: c, label: c }))}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Giá gốc mỗi cái" inputMode="decimal" value={f.unit_price_amount} onChange={set("unit_price_amount")} trailing={f.currency} />
          <Input label="Cân nặng" inputMode="numeric" value={f.weight_grams} onChange={set("weight_grams")} trailing="g" />
          <Input
            label="Cước nội địa"
            inputMode="numeric"
            value={f.domestic_shipping_vnd}
            onChange={set("domestic_shipping_vnd")}
            placeholder={p ? String(p.domestic_shipping_vnd) : ""}
            trailing="đ"
          />
          <Input label="Đóng gói" inputMode="numeric" value={f.packaging_vnd} onChange={set("packaging_vnd")} placeholder={p ? String(p.packaging_vnd) : ""} trailing="đ" />
          <Input label="Phí khác" inputMode="numeric" value={f.other_fees_vnd} onChange={set("other_fees_vnd")} trailing="đ" />
        </div>
        <Switch
          label="Tự tính lại khi tỷ giá, cước đổi"
          description={f.auto_update ? `Theo tham số chung (tỷ giá ${fxDefault ? formatVnd(num(fxDefault)) : "—"}/${f.currency}).` : "Dùng tham số riêng cho món này."}
          checked={f.auto_update}
          onChange={(v) => setF((x) => ({ ...x, auto_update: v }))}
        />
        {!f.auto_update ? (
          <div className="grid grid-cols-2 gap-3">
            <Input label="Tỷ giá riêng" inputMode="decimal" value={f.fx_rate} onChange={set("fx_rate")} placeholder={fxDefault ? String(num(fxDefault)) : ""} trailing="đ" />
            <Input label="Thuế GTGT riêng" inputMode="decimal" value={f.vat_pct} onChange={set("vat_pct")} placeholder={p ? String(num(p.vat_pct)) : ""} trailing="%" />
          </div>
        ) : null}
        <Button
          disabled={!valid}
          loading={save.isPending}
          onClick={async () => {
            await save.mutateAsync(body);
            notifySuccess("Đã lưu giá vốn về tay");
          }}
        >
          {sheet ? "Lưu bản mới" : "Lưu giá vốn"}
        </Button>
        {sheet ? (
          <p className="text-[13px] text-ink-2">
            Bản {sheet.version}
            {sheet.recalculated_at ? (
              <>
                {" · tính lúc "}
                <DateTime value={sheet.recalculated_at} format="dateTime" />
              </>
            ) : null}
          </p>
        ) : null}
      </Card>
      <Card className="flex flex-col gap-2">
        <SectionLabel>Từng khoản cho một cái</SectionLabel>
        {!valid ? (
          <p className="text-[14px] text-ink-2">Nhập giá gốc để xem giá vốn.</p>
        ) : preview.error ? (
          <p className="text-[14px] text-seal">{preview.error.message}</p>
        ) : preview.data ? (
          <>
            <DataList
              items={[
                ...preview.data.breakdown.map((l) => ({
                  label: (
                    <span>
                      {l.label}
                      <span className="block text-[12.5px] text-ink-3">{l.formula}</span>
                    </span>
                  ),
                  value: <Money value={l.amount_vnd} />,
                })),
                { label: "Giá vốn về tay", value: <Money value={preview.data.landed_cost_vnd} />, strong: true },
              ]}
            />
            {sheet && sheet.landed_cost_vnd !== preview.data.landed_cost_vnd ? (
              <p className="text-[13px] text-review">Đang lưu: <Money value={sheet.landed_cost_vnd} />. Bấm lưu để cập nhật.</p>
            ) : null}
          </>
        ) : (
          <SkeletonList rows={2} />
        )}
      </Card>
    </div>
  );
}

function PriceSection({ candidateId, hasSheet }: { candidateId: string; hasSheet: boolean }) {
  const params = useCostParams();
  const list = usePriceProposals(candidateId);
  const propose = useProposePrice();
  const [margin, setMargin] = useState("");
  const latest = list.data?.find((p) => p.status !== "superseded");
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Đề xuất giá bán</SectionLabel>
        <LevelTag level="review" size="sm" />
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Input
          label="Biên mục tiêu"
          inputMode="decimal"
          value={margin}
          onChange={(e) => setMargin(e.target.value)}
          placeholder={params.data ? String(num(params.data.target_margin_pct)) : ""}
          trailing="%"
          wrapperClassName="w-36"
        />
        <Button
          icon={<Sparkles className="size-4" aria-hidden />}
          disabled={!hasSheet}
          loading={propose.isPending}
          onClick={async () => {
            await propose.mutateAsync({ candidate_id: candidateId, target_margin_pct: margin ? Number(margin) : undefined });
            notifySuccess("AI đã đề xuất giá, chị xem rồi duyệt");
          }}
        >
          AI đề xuất giá
        </Button>
      </div>
      {!hasSheet ? <p className="text-[14px] text-ink-2">Lưu giá vốn trước, AI mới đề xuất giá được.</p> : null}
      {latest ? <ProposalCard key={latest.id + latest.status} p={latest} /> : null}
    </section>
  );
}

const PROPOSAL_STATUS: Record<PriceProposal["status"], string> = {
  draft: "Nháp",
  pending_review: "Chờ chị duyệt",
  approved: "Đã duyệt",
  rejected: "Chị đã trả lại",
  superseded: "Đã thay",
};

function ProposalCard({ p }: { p: PriceProposal }) {
  const { user } = useSession();
  const approve = useApproveItem();
  const ret = useReturnItem();
  const [price, setPrice] = useState(String(p.proposed_price_vnd));
  const [note, setNote] = useState("");
  const pending = p.status === "pending_review" && !!p.approval_item_id && user?.role === "owner";
  const priceNum = Math.round(Number(price) || 0);
  const margin = priceNum > 0 ? Math.round(((priceNum - p.landed_cost_vnd) * 100) / priceNum) : 0;
  return (
    <Card tone={p.status === "approved" ? "accent" : "default"} className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] text-ink-2">Giá đề xuất</p>
          <p className="font-display text-[28px] leading-tight font-extrabold">
            <Money value={p.approved_price_vnd ?? p.proposed_price_vnd} />
          </p>
          {p.proposed_drop_price_vnd ? (
            <p className="text-[13px] text-ink-2">
              Giá mở đợt <Money value={p.proposed_drop_price_vnd} />
            </p>
          ) : null}
        </div>
        <Badge tone={p.status === "approved" ? "success" : p.status === "rejected" ? "danger" : "warning"}>{PROPOSAL_STATUS[p.status]}</Badge>
      </div>
      <DataList
        items={[
          { label: "Giá vốn về tay", value: <Money value={p.landed_cost_vnd} /> },
          { label: "Biên lợi nhuận", value: `${num(p.margin_pct).toLocaleString("vi-VN")}%` },
          {
            label: `Thị trường (${p.market_samples} nơi bán)`,
            value: p.market_median_vnd ? (
              <span>
                <Money value={p.market_low_vnd ?? p.market_median_vnd} compact />–<Money value={p.market_high_vnd ?? p.market_median_vnd} compact />
              </span>
            ) : (
              "Chưa có"
            ),
          },
        ]}
      />
      {p.rationale ? <p className="text-[14px] whitespace-pre-line text-ink-2">{p.rationale}</p> : null}
      {pending ? (
        <div className="flex flex-col gap-3 border-t border-line pt-3">
          <Input label="Giá chị chốt" inputMode="numeric" value={price} onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} trailing="đ" hint={`Biên ${margin}%`} />
          <Textarea aria-label="Lời nhắn khi trả lại" value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Nếu trả lại: ghi vì sao (ví dụ: cao quá)" />
          <div className="flex flex-wrap justify-end gap-2 max-md:[&>button]:flex-1">
            <Button
              variant="secondary"
              icon={<X className="size-4" aria-hidden />}
              disabled={!note.trim()}
              loading={ret.isPending}
              onClick={async () => {
                await ret.mutateAsync({ id: p.approval_item_id!, note: note.trim() });
                notifySuccess("Đã trả lại đề xuất");
              }}
            >
              Trả lại
            </Button>
            <Button
              icon={<Check className="size-4" aria-hidden />}
              disabled={priceNum <= 0}
              loading={approve.isPending}
              onClick={async () => {
                await approve.mutateAsync({ id: p.approval_item_id!, payload: priceNum !== p.proposed_price_vnd ? { price_vnd: priceNum } : undefined });
                notifySuccess("Đã duyệt giá bán");
              }}
            >
              Duyệt giá {formatVnd(priceNum)}
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
