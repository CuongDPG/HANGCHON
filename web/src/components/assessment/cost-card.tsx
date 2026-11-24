"use client";

import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Badge, Card, CardHeader, DataList, Money } from "@/components/ui";
import type { CostView, MarketView } from "@/lib/api/assessment";
import { platformLabel } from "@/lib/api/sourcing";
import { formatVndCompact } from "@/lib/format";

/** Giá vốn về tay (cost_sheets của Nguồn cung nếu có, không thì ước tính sơ bộ) + giá ở Việt Nam (b5). */
export function CostCard({ cost, market }: { cost: CostView | null; market: MarketView | null }) {
  const [showListings, setShowListings] = useState(false);
  return (
    <Card className="flex flex-col gap-3">
      <CardHeader
        title={cost ? <>Giá vốn về tay · <Money value={cost.landed_cost_vnd} /></> : "Giá vốn về tay"}
        aside={cost?.source === "estimate" ? <Badge tone="warning">Ước tính sơ bộ</Badge> : cost ? <Badge tone="success">Theo Nguồn cung</Badge> : null}
      />
      {cost ? (
        <>
          <DataList items={cost.lines.map((l) => ({ label: l.label, value: <Money value={l.amount_vnd} /> }))} />
          <p className="text-[12.5px] text-ink-3">
            {cost.note}
            {cost.assumptions.length ? ` ${cost.assumptions.join(". ")}.` : ""}
          </p>
        </>
      ) : (
        <p className="text-sm text-ink-2">Chưa có giá gốc để tính.</p>
      )}
      {market ? (
        <div className="border-t border-line pt-3 text-sm">
          <p>
            Hàng tương tự ở Việt Nam: <strong>{formatVndCompact(market.low_vnd)}–{formatVndCompact(market.high_vnd)}</strong> ({market.count} tin rao).
          </p>
          {market.margin_pct !== null ? (
            <p className="mt-0.5">
              Bán <strong>{formatVndCompact(market.suggested_price_vnd)}</strong> thì biên{" "}
              <strong className={market.margin_pct >= 30 ? "text-auto" : market.margin_pct >= 15 ? "text-review" : "text-seal"}>
                {Math.round(market.margin_pct)}%
              </strong>
              .
            </p>
          ) : null}
          <button type="button" className="mt-1 text-[13px] font-medium text-accent" onClick={() => setShowListings((v) => !v)}>
            {showListings ? "Ẩn tin rao" : "Xem các tin rao"}
          </button>
          {showListings ? (
            <ul className="mt-2 flex flex-col gap-1.5">
              {market.listings.map((l) => (
                <li key={l.id} className="flex items-center justify-between gap-3 text-[13px]">
                  <a href={l.url} target="_blank" rel="noreferrer" className="flex min-w-0 items-center gap-1 text-ink-2 hover:text-ink">
                    <ExternalLink className="size-3 shrink-0" aria-hidden />
                    <span className="truncate">
                      {platformLabel(l.platform)} · {l.shop_name ?? l.title}
                    </span>
                  </a>
                  <span className="shrink-0 tabular-nums">
                    <Money value={l.price_vnd} />
                    {l.match_confidence && Number(l.match_confidence) < 0.6 ? <span className="ml-1 text-ink-3">(chưa chắc cùng món)</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
