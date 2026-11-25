"use client";

import { History, Plus, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  DateTime,
  EmptyState,
  InlineSelect,
  Input,
  LevelTag,
  notifySuccess,
  Segmented,
  Sheet,
  SkeletonList,
} from "@/components/ui";
import {
  useAdjustInventory,
  useCreateInventory,
  useInventory,
  useInventoryMovements,
  useSetThreshold,
  useStockCandidates,
  type AdjustKind,
  type InventoryRow,
} from "@/lib/api/orders";

const KIND_OPTIONS: { value: AdjustKind; label: string }[] = [
  { value: "received", label: "Nhập thêm" },
  { value: "damaged", label: "Hỏng / mất" },
  { value: "other", label: "Lý do khác" },
];

function toInt(v: string): number | null {
  const s = v.trim().replace(/[^\d-]/g, "");
  if (!s || s === "-") return null;
  const n = Number(s);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/** g8 Tồn kho nhỏ: số các món giữ sẵn, nhập tồn đầu kỳ, điều chỉnh tay có lý do, ngưỡng báo sắp hết theo món. */
export function InventoryTab() {
  const q = useInventory();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<InventoryRow | null>(null);
  const defaultThreshold = q.data?.[0]?.default_threshold;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex flex-wrap items-center gap-2 text-[14px] text-ink-2">
          <LevelTag level="auto" size="sm">AI báo khi sắp hết</LevelTag>
          {defaultThreshold !== undefined ? (
            <span>
              Ngưỡng chung: còn ≤ {defaultThreshold} cái (đổi ở{" "}
              <Link href="/desk/cai-dat" className="text-accent">
                Cài đặt
              </Link>
              ), từng món đặt riêng được.
            </span>
          ) : null}
        </p>
        <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
          Thêm món giữ sẵn
        </Button>
      </div>
      {q.isPending ? (
        <SkeletonList rows={3} />
      ) : q.isError ? (
        <EmptyState tone="error" title="Chưa tải được" description={q.error.message} />
      ) : !q.data.length ? (
        <EmptyState
          title="Chưa có món giữ sẵn"
          description="Chị thêm món và số tồn đầu kỳ; mỗi đơn bán, giao, nhập lô sẽ tự cộng trừ."
          action={
            <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
              Thêm món giữ sẵn
            </Button>
          }
        />
      ) : (
        <Card flush>
          <div className="hidden grid-cols-[minmax(0,1fr)_5rem_5rem_5rem_6.5rem_8rem_7rem] gap-3 border-b border-line px-3 py-2 text-[12.5px] text-ink-2 md:grid">
            <span>Món</span>
            <span className="text-right">Trong kho</span>
            <span className="text-right">Đã giữ</span>
            <span className="text-right">Đơn chờ</span>
            <span className="text-right">Còn bán được</span>
            <span>Báo khi còn ≤</span>
            <span />
          </div>
          <ul className="divide-y divide-line">
            {q.data.map((r) => (
              <li key={r.inventory_item_id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-3 py-3 md:grid-cols-[minmax(0,1fr)_5rem_5rem_5rem_6.5rem_8rem_7rem]">
                <span className="min-w-0">
                  <span className="block truncate text-[15px] font-semibold">{r.name}</span>
                  <span className="text-[12.5px] text-ink-2 md:hidden">
                    Trong kho {r.on_hand} · đã giữ {r.reserved} · đơn chờ {r.pending_orders_qty} · báo khi ≤ {r.low_stock_threshold}
                    {r.threshold_is_default ? " (chung)" : ""}
                  </span>
                  {r.last_counted_at ? (
                    <span className="hidden text-[12.5px] text-ink-2 md:block">
                      Đếm lần cuối <DateTime value={r.last_counted_at} format="date" />
                    </span>
                  ) : null}
                </span>
                <span className="hidden text-right tabular-nums md:block">{r.on_hand}</span>
                <span className="hidden text-right tabular-nums text-ink-2 md:block">{r.reserved}</span>
                <span className="hidden text-right tabular-nums text-ink-2 md:block">{r.pending_orders_qty}</span>
                <span className="flex items-center justify-end gap-2 md:row-auto">
                  {r.low ? <Badge tone="danger">Sắp hết</Badge> : null}
                  <span className="font-display text-[20px] font-extrabold tabular-nums">{r.available}</span>
                </span>
                <span className="hidden text-[14px] md:block">
                  {r.low_stock_threshold} cái <span className="text-ink-2">{r.threshold_is_default ? "· chung" : "· riêng"}</span>
                </span>
                <Button size="sm" variant="secondary" className="col-span-2 justify-self-start md:col-span-1 md:justify-self-end" icon={<SlidersHorizontal className="size-4" />} onClick={() => setEditing(r)}>
                  Điều chỉnh
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <AddStockSheet open={adding} onClose={() => setAdding(false)} />
      <AdjustSheet row={editing} onClose={() => setEditing(null)} />
    </div>
  );
}

function AddStockSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const cands = useStockCandidates(open);
  const create = useCreateInventory();
  const [pick, setPick] = useState<string | null>(null);
  const [qty, setQty] = useState("");
  const [threshold, setThreshold] = useState("");
  const [note, setNote] = useState("");
  const options = (cands.data ?? []).map((c) => ({ value: `${c.product_id}|${c.variant_id ?? ""}`, label: c.name }));
  const onHand = toInt(qty);
  const close = () => {
    setPick(null);
    setQty("");
    setThreshold("");
    setNote("");
    onClose();
  };
  const submit = () => {
    if (!pick || onHand === null || onHand < 0) return;
    const [product_id, variant_id] = pick.split("|");
    create.mutate(
      { product_id, variant_id: variant_id || null, on_hand: onHand, low_stock_threshold: toInt(threshold), note: note.trim() || undefined },
      { onSuccess: (r) => (notifySuccess(`Đã thêm ${r.name}: ${r.on_hand} cái`), close()) },
    );
  };
  return (
    <Sheet
      open={open}
      onClose={close}
      title="Thêm món giữ sẵn"
      description="Đặt số tồn đầu kỳ. Từ đây mỗi đơn bán, giao, nhập lô sẽ tự cộng trừ."
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Huỷ
          </Button>
          <Button loading={create.isPending} disabled={!pick || onHand === null || onHand < 0} onClick={submit}>
            Thêm vào tồn kho
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {cands.isError ? <p className="text-[14px] text-seal">{cands.error.message}</p> : null}
        <InlineSelect
          label="Món"
          value={pick}
          placeholder={cands.isPending ? "Đang tải…" : options.length ? "Chọn món" : "Món nào cũng đã có tồn kho"}
          disabled={!options.length}
          onChange={setPick}
          options={options}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Tồn đầu kỳ" inputMode="numeric" trailing="cái" required value={qty} onChange={(e) => setQty(e.target.value)} />
          <Input label="Báo khi còn ≤" hint="Bỏ trống = ngưỡng chung" inputMode="numeric" trailing="cái" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
        </div>
        <Input label="Ghi chú" placeholder="vd Kiểm kho đầu tháng" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
    </Sheet>
  );
}

function AdjustSheet({ row: current, onClose }: { row: InventoryRow | null; onClose: () => void }) {
  // giữ dòng vừa mở để hộp đóng êm (không chớp thành hộp trống)
  const [kept, setKept] = useState<InventoryRow | null>(current);
  if (current && current !== kept) setKept(current);
  const row = current ?? kept;
  const adjust = useAdjustInventory();
  const setThr = useSetThreshold();
  const moves = useInventoryMovements(row?.inventory_item_id ?? null);
  const [mode, setMode] = useState<"delta" | "set">("delta");
  const [qty, setQty] = useState("");
  const [kind, setKind] = useState<AdjustKind>("received");
  const [reason, setReason] = useState("");
  const [thr, setThr2] = useState<string | null>(null);
  const n = toInt(qty);
  const target = row && n !== null ? (mode === "set" ? n : row.on_hand + n) : null;
  const invalid = n === null || (mode === "delta" && n === 0) || (target !== null && target < 0) || reason.trim().length < 2;
  const close = () => {
    setQty("");
    setReason("");
    setThr2(null);
    setMode("delta");
    onClose();
  };
  if (!row) return null;
  const thrValue = thr ?? (row.threshold_is_default ? "" : String(row.low_stock_threshold ?? ""));
  return (
    <Sheet open={!!current} onClose={close} title={`Điều chỉnh tồn · ${row.name}`} description={`Trong kho ${row.on_hand} · còn bán được ${row.available}`} size="lg">
      <div className="flex flex-col gap-5 md:grid md:grid-cols-2 md:gap-6">
        <section className="flex flex-col gap-3" aria-label="Điều chỉnh số lượng">
          <Segmented
            aria-label="Cách điều chỉnh"
            value={mode}
            onChange={setMode}
            options={[
              { value: "delta", label: "Cộng / trừ" },
              { value: "set", label: "Đếm lại (đặt đúng số)" },
            ]}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={mode === "set" ? "Số đếm được" : "Số lượng (+/−)"}
              hint={mode === "delta" ? "vd 10 hoặc -2" : undefined}
              inputMode="numeric"
              trailing="cái"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              error={target !== null && target < 0 ? "Tồn không được âm" : undefined}
            />
            {mode === "delta" ? <InlineSelect label="Loại" value={kind} onChange={setKind} options={KIND_OPTIONS} /> : <div />}
          </div>
          <Input label="Lý do" required placeholder="vd Rách 2 cái khi kiểm hàng" value={reason} onChange={(e) => setReason(e.target.value)} />
          {target !== null && target >= 0 ? (
            <p className="text-[14px]">
              Trong kho: {row.on_hand} → <b>{target}</b> cái
            </p>
          ) : null}
          <Button
            className="self-start"
            loading={adjust.isPending}
            disabled={invalid}
            onClick={() =>
              n !== null &&
              adjust.mutate(
                { id: row.inventory_item_id, mode, quantity: n, kind: mode === "set" ? "count" : kind, reason: reason.trim() },
                { onSuccess: (r) => (notifySuccess(`Đã ghi: trong kho ${r.on_hand} cái`), close()) },
              )
            }
          >
            Ghi điều chỉnh
          </Button>
          <div className="mt-2 flex flex-col gap-2 border-t border-line pt-4">
            <h3 className="font-sans text-[14px] font-semibold">Ngưỡng báo sắp hết</h3>
            <div className="flex flex-wrap items-end gap-2">
              <Input
                wrapperClassName="w-40"
                label="Báo khi còn ≤"
                inputMode="numeric"
                trailing="cái"
                placeholder={String(row.default_threshold)}
                value={thrValue}
                onChange={(e) => setThr2(e.target.value)}
              />
              <Button
                size="sm"
                variant="secondary"
                loading={setThr.isPending}
                disabled={thr === null}
                onClick={() =>
                  setThr.mutate(
                    { id: row.inventory_item_id, low_stock_threshold: toInt(thrValue) },
                    { onSuccess: (r) => (setThr2(null), notifySuccess(r.threshold_is_default ? "Dùng ngưỡng chung" : `Báo khi còn ≤ ${r.low_stock_threshold} cái`)) },
                  )
                }
              >
                Lưu ngưỡng
              </Button>
            </div>
            <p className="text-[12.5px] text-ink-2">Bỏ trống rồi lưu để dùng ngưỡng chung ({row.default_threshold} cái).</p>
          </div>
        </section>
        <section className="flex flex-col gap-2" aria-label="Lịch sử tồn">
          <h3 className="flex items-center gap-1.5 font-sans text-[14px] font-semibold">
            <History className="size-4" aria-hidden /> Lịch sử
          </h3>
          {moves.isPending ? (
            <SkeletonList rows={3} />
          ) : moves.isError ? (
            <p className="text-[14px] text-seal">{moves.error.message}</p>
          ) : !moves.data.length ? (
            <p className="text-[14px] text-ink-2">Chưa có thay đổi nào.</p>
          ) : (
            <ul className="flex max-h-[26rem] flex-col divide-y divide-line overflow-y-auto rounded-md border border-line">
              {moves.data.map((m) => (
                <li key={m.id} className="flex items-start justify-between gap-3 px-3 py-2 text-[13.5px]">
                  <span className="min-w-0">
                    <span className="block font-medium">{m.reason_label}</span>
                    {m.note ? <span className="block text-ink-2">{m.note}</span> : null}
                    <span className="text-[12.5px] text-ink-2">
                      <DateTime value={m.created_at} format="dateTime" />
                      {m.created_by_name ? ` · ${m.created_by_name}` : ""}
                    </span>
                  </span>
                  <span className={m.delta_on_hand < 0 ? "shrink-0 font-semibold text-seal tabular-nums" : "shrink-0 font-semibold tabular-nums"}>
                    {m.delta_on_hand > 0 ? `+${m.delta_on_hand}` : m.delta_on_hand}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Sheet>
  );
}
