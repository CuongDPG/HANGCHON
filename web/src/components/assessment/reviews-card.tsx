"use client";

import { useState } from "react";
import { Card, CardHeader, LevelTag, Sheet } from "@/components/ui";
import type { DigestPoint, ReviewDigest } from "@/lib/api/assessment";
import { formatNumber } from "@/lib/format";

function Quotes({ point, onClose }: { point: DigestPoint | null; onClose: () => void }) {
  return (
    <Sheet open={!!point} onClose={onClose} title={point?.point ?? ""} description={point ? `${point.count} lượt nhắc · trích đánh giá gốc đã dịch` : undefined}>
      <ul className="flex flex-col gap-3">
        {point?.quotes.map((q) => (
          <li key={q.id} className="rounded-md border border-line p-3">
            <p className="text-[13px] text-ink-3">{"★".repeat(q.rating)}</p>
            <p className="text-[15px]">{q.vi ?? "(chưa dịch)"}</p>
            <p className="mt-1 text-[13px] text-ink-3">Gốc: {q.original}</p>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

function Points({ label, items, onPick }: { label: string; items: DigestPoint[]; onPick: (p: DigestPoint) => void }) {
  if (!items.length) return null;
  return (
    <p className="text-sm">
      <span className="font-medium">{label}: </span>
      {items.slice(0, 4).map((p, i) => (
        <span key={p.point}>
          {i ? ", " : ""}
          <button type="button" className="text-left underline decoration-line-strong underline-offset-2 hover:decoration-ink" onClick={() => onPick(p)}>
            {p.point.toLowerCase()} ({p.count})
          </button>
        </span>
      ))}
    </p>
  );
}

/** b2 — Đọc hộ đánh giá: khen/chê lặp lại kèm số lượt nhắc, tách riêng 1–2 sao, bấm xem trích dẫn gốc đã dịch. */
export function ReviewsCard({ d, total }: { d: ReviewDigest; total: number | null }) {
  const [pick, setPick] = useState<DigestPoint | null>(null);
  const [showLow, setShowLow] = useState(false);
  const hist = d.rating_histogram;
  const max = Math.max(1, ...Object.values(hist));
  return (
    <Card className="flex flex-col gap-2">
      <CardHeader
        title={`AI đã đọc ${formatNumber(d.reviews_read)} đánh giá${total && total > d.reviews_read ? ` (trên ${formatNumber(total)})` : ""}`}
        aside={<LevelTag level="auto" size="sm" />}
      />
      <div className="grid grid-cols-[2rem_1fr_2rem] items-center gap-x-2 gap-y-1 text-[12.5px] text-ink-2" aria-label="Phân bố số sao">
        {["5", "4", "3", "2", "1"].map((k) => (
          <div key={k} className="contents">
            <span>{k}★</span>
            <span className="h-1.5 rounded-full bg-soft">
              <span className={`block h-full rounded-full ${Number(k) <= 2 ? "bg-seal" : "bg-ink-3"}`} style={{ width: `${((hist[k] ?? 0) / max) * 100}%` }} />
            </span>
            <span className="text-right tabular-nums">{hist[k] ?? 0}</span>
          </div>
        ))}
      </div>
      <Points label="Khen" items={d.praise} onPick={setPick} />
      <Points label="Chê" items={d.complaints} onPick={setPick} />
      {d.low_star_summary ? (
        <div className="rounded-md bg-seal-wash/60 p-3 text-sm">
          <p>
            <span className="font-medium">1–2 sao: </span>
            {d.low_star_summary}
          </p>
          {d.low_star_reviews.length ? (
            <button type="button" className="mt-1 text-[13px] font-medium text-seal" onClick={() => setShowLow((v) => !v)}>
              {showLow ? "Ẩn" : `Đọc ${d.low_star_reviews.length} đánh giá này`}
            </button>
          ) : null}
          {showLow ? (
            <ul className="mt-2 flex flex-col gap-2">
              {d.low_star_reviews.map((r) => (
                <li key={r.id} className="text-[13px]">
                  <span className="text-ink-3">{"★".repeat(r.rating)}</span> {r.vi ?? r.original}
                  <span className="block text-ink-3">Gốc: {r.original}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {d.suspicious_notes ? <p className="text-[13px] text-ink-2">{d.suspicious_notes}</p> : null}
      <Quotes point={pick} onClose={() => setPick(null)} />
    </Card>
  );
}
