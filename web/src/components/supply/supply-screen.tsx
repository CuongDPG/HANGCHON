"use client";

import { AlertTriangle, Calculator, Factory, Package, Plus, Settings2, Truck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  Badge,
  Button,
  CardLink,
  DateTime,
  EmptyState,
  IconLink,
  InlineSelect,
  Input,
  Money,
  PageHeader,
  ProgressBar,
  Sheet,
  SkeletonList,
  Tabs,
  Textarea,
  notifySuccess,
} from "@/components/ui";
import {
  INBOUND_FLOW,
  INBOUND_LABELS,
  LANGUAGE_LABELS,
  PO_KIND_LABELS,
  SUPPLIER_KIND_LABELS,
  useCostSheets,
  useDocWarnings,
  useInboundList,
  usePurchaseOrders,
  useSaveSupplier,
  useSuppliers,
  type SupplierKind,
} from "@/lib/api/supply";
import { POStatusBadge, UploadSheet } from "./shared";

type Tab = "don" | "lo-hang" | "ncc" | "gia-von" | "chung-tu";
const TABS: { value: Tab; label: string }[] = [
  { value: "don", label: "Đơn đặt" },
  { value: "lo-hang", label: "Hàng về" },
  { value: "ncc", label: "Nhà cung cấp" },
  { value: "gia-von", label: "Giá vốn" },
  { value: "chung-tu", label: "Chứng từ" },
];

/** Nguồn cung (d1–d7): đơn đặt mẫu/lô, lô hàng về, sổ nhà cung cấp, giá vốn, chứng từ nguồn gốc. */
export function SupplyScreen() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const t = params.get("tab") as Tab | null;
  const tab: Tab = t && TABS.some((x) => x.value === t) ? t : "don";
  const candidate = params.get("candidate");
  const warnings = useDocWarnings();

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Nguồn cung"
        actions={<IconLink href="/desk/nguon-cung/cai-dat" label="Tham số giá vốn" icon={<Settings2 />} />}
      />
      <Tabs
        aria-label="Mục nguồn cung"
        value={tab}
        onChange={(v) => router.replace(`${pathname}?tab=${v}`, { scroll: false })}
        items={TABS.map((x) => ({ ...x, count: x.value === "chung-tu" && warnings.data?.length ? warnings.data.length : undefined }))}
      />
      {tab === "don" ? <OrdersTab candidateId={candidate} /> : null}
      {tab === "lo-hang" ? <InboundTab /> : null}
      {tab === "ncc" ? <SuppliersTab /> : null}
      {tab === "gia-von" ? <CostTab /> : null}
      {tab === "chung-tu" ? <DocsTab /> : null}
    </div>
  );
}

function OrdersTab({ candidateId }: { candidateId: string | null }) {
  const { data, isPending, error } = usePurchaseOrders(candidateId ? { candidate_id: candidateId } : {});
  if (isPending) return <SkeletonList rows={3} />;
  if (error) return <EmptyState tone="error" title="Chưa tải được đơn" description={error.message} />;
  if (!data.items.length)
    return (
      <EmptyState
        icon={<Package />}
        title="Chưa có đơn đặt nào"
        description="Chuyển một món sang cột «Mua mẫu» trên bàn chọn, AI sẽ soạn đơn đặt mẫu để chị duyệt. Đóng đợt bán thì AI soạn đơn đặt lô."
      />
    );
  return (
    <ul className="flex flex-col gap-2">
      {data.items.map((po) => (
        <li key={po.id}>
          <CardLink href={`/desk/nguon-cung/don/${po.id}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[13px] text-ink-2">
                  {PO_KIND_LABELS[po.kind]} · {po.code}
                </p>
                <h3 className="truncate text-[15px] font-semibold">{po.candidate_title ?? po.lines[0]?.description ?? "Đơn đặt hàng"}</h3>
                <p className="truncate text-[14px] text-ink-2">
                  {po.supplier_name ?? "Chưa rõ nhà cung cấp"}
                  {po.agent_name ? ` · qua ${po.agent_name}` : ""}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <POStatusBadge status={po.status} />
                <span className="text-[15px] font-semibold">
                  <Money value={po.total_vnd} />
                </span>
              </div>
            </div>
            {po.missing_documents.length ? (
              <p className="mt-2 flex items-center gap-1.5 text-[13px] text-review">
                <AlertTriangle className="size-4" aria-hidden /> Thiếu {po.missing_documents.length} chứng từ
              </p>
            ) : null}
          </CardLink>
        </li>
      ))}
    </ul>
  );
}

function InboundTab() {
  const { data, isPending, error } = useInboundList();
  if (isPending) return <SkeletonList rows={3} />;
  if (error) return <EmptyState tone="error" title="Chưa tải được lô hàng" description={error.message} />;
  if (!data.items.length)
    return <EmptyState icon={<Truck />} title="Chưa có lô hàng nào đang về" description="Đơn đã gửi cho bên bán sẽ tự có một lô hàng để theo dõi." />;
  return (
    <ul className="flex flex-col gap-2">
      {data.items.map((s) => {
        const step = s.status === "problem" ? 0 : INBOUND_FLOW.indexOf(s.status) + 1;
        return (
          <li key={s.id}>
            <CardLink href={`/desk/nguon-cung/lo/${s.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13px] text-ink-2">
                    {s.po_code ?? "Lô lẻ"}
                    {s.code ? ` · ${s.code}` : ""}
                  </p>
                  <h3 className="text-[15px] font-semibold">{INBOUND_LABELS[s.status]}</h3>
                  <p className="truncate text-[14px] text-ink-2">{s.supplier_name ?? s.carrier ?? "—"}</p>
                </div>
                <div className="shrink-0 text-right text-[13px] text-ink-2">
                  {s.received_at ? (
                    <>
                      Về <DateTime value={s.received_at} format="dayMonth" />
                    </>
                  ) : s.eta ? (
                    <>
                      Dự kiến <DateTime value={s.eta} format="dayMonth" />
                    </>
                  ) : null}
                  {s.status === "problem" ? <Badge tone="danger">Có vấn đề</Badge> : null}
                </div>
              </div>
              <ProgressBar
                className="mt-3"
                size="sm"
                value={step}
                max={INBOUND_FLOW.length}
                tone={s.status === "delivered" ? "success" : s.status === "problem" ? "danger" : "accent"}
                label={`Mốc ${step} trên ${INBOUND_FLOW.length}`}
              />
            </CardLink>
          </li>
        );
      })}
    </ul>
  );
}

function SuppliersTab() {
  const { data, isPending, error } = useSuppliers();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-3">
      <Button size="sm" className="self-start" icon={<Plus className="size-4" aria-hidden />} onClick={() => setOpen(true)}>
        Thêm nhà cung cấp
      </Button>
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : !data.items.length ? (
        <EmptyState icon={<Factory />} title="Sổ nhà cung cấp còn trống" description="Thêm shop, xưởng hoặc đơn vị mua hộ chị hay làm việc." />
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.map((s) => (
            <li key={s.id}>
              <CardLink href={`/desk/nguon-cung/ncc/${s.id}`}>
                <div className="flex items-center gap-3">
                  <div className="grid size-12 shrink-0 place-items-center rounded-md bg-soft font-display text-lg font-bold tabular-nums">
                    {s.trust_score ?? "–"}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-[15px] font-semibold">{s.name}</h3>
                    <p className="truncate text-[13px] text-ink-2">
                      {SUPPLIER_KIND_LABELS[s.kind]} · {s.country ?? "—"} · {LANGUAGE_LABELS[s.language] ?? s.language}
                    </p>
                    <p className="truncate text-[13px] text-ink-2">
                      <span className={s.is_blocked ? "text-seal" : s.trust_score && s.trust_score >= 80 ? "text-auto" : ""}>{s.trust_label}</span>
                      {s.trust_score !== null ? ` · ${s.trust_basis}` : ""}
                    </p>
                  </div>
                </div>
              </CardLink>
            </li>
          ))}
        </ul>
      )}
      <Sheet open={open} onClose={() => setOpen(false)} title="Thêm nhà cung cấp">
        {open ? <SupplierForm onClose={() => setOpen(false)} /> : null}
      </Sheet>
    </div>
  );
}

export function SupplierForm({
  onClose,
  initial,
}: {
  onClose: () => void;
  initial?: { id: string; name: string; name_original: string | null; kind: SupplierKind; country: string | null; language: string; shop_url: string | null; notes: string | null };
}) {
  const [kind, setKind] = useState<SupplierKind>(initial?.kind ?? "shop");
  const [language, setLanguage] = useState(initial?.language ?? "zh");
  const save = useSaveSupplier();
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        const f = new FormData(e.currentTarget);
        const name = String(f.get("name") ?? "").trim();
        if (name.length < 2) {
          setError("Chị đặt tên nhà cung cấp nhé.");
          return;
        }
        const country = String(f.get("country") ?? "").trim();
        await save.mutateAsync({
          id: initial?.id,
          name,
          name_original: String(f.get("name_original") ?? "") || null,
          kind,
          language,
          country: country.length === 2 ? country : null,
          shop_url: String(f.get("shop_url") ?? "") || null,
          notes: String(f.get("notes") ?? "") || null,
        });
        notifySuccess(initial ? "Đã lưu" : "Đã thêm nhà cung cấp");
        onClose();
      }}
    >
      <Input name="name" label="Tên gọi" defaultValue={initial?.name} error={error} required />
      <Input name="name_original" label="Tên gốc (tiếng Trung/Nhật)" defaultValue={initial?.name_original ?? ""} />
      <InlineSelect
        label="Loại"
        value={kind}
        onChange={setKind}
        options={(Object.keys(SUPPLIER_KIND_LABELS) as SupplierKind[]).map((k) => ({ value: k, label: SUPPLIER_KIND_LABELS[k] }))}
      />
      <div className="grid grid-cols-2 gap-3">
        <InlineSelect label="Ngôn ngữ nhắn" value={language} onChange={setLanguage} options={["zh", "ja", "vi", "en"].map((l) => ({ value: l, label: LANGUAGE_LABELS[l] }))} />
        <Input name="country" label="Nước (CN, JP…)" maxLength={2} defaultValue={initial?.country ?? ""} />
      </div>
      <Input name="shop_url" label="Link shop" defaultValue={initial?.shop_url ?? ""} />
      <Textarea name="notes" label="Ghi chú" defaultValue={initial?.notes ?? ""} rows={2} />
      <div className="flex justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button type="submit" loading={save.isPending}>
          Lưu
        </Button>
      </div>
    </form>
  );
}

function CostTab() {
  const { data, isPending, error } = useCostSheets();
  if (isPending) return <SkeletonList rows={3} />;
  if (error) return <EmptyState tone="error" title="Chưa tải được giá vốn" description={error.message} />;
  if (!data.items.length)
    return <EmptyState icon={<Calculator />} title="Chưa tính giá vốn món nào" description="Mở một món trên bàn chọn rồi bấm «Tính giá vốn»." />;
  return (
    <ul className="flex flex-col gap-2">
      {data.items.map((s) => (
        <li key={s.id}>
          <CardLink href={`/desk/nguon-cung/gia-von/${s.candidate_id}`}>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-[15px] font-semibold">{s.candidate_title ?? "Món đã xoá"}</h3>
                <p className="truncate text-[13px] text-ink-2">
                  {Number(s.unit_price_amount).toLocaleString("vi-VN")} {s.currency}
                  {s.weight_grams ? ` · ${(s.weight_grams / 1000).toLocaleString("vi-VN")} kg` : ""}
                  {s.auto_update ? " · tự cập nhật" : " · tham số riêng"}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-[13px] text-ink-2">Về tay</p>
                <p className="text-[16px] font-semibold">
                  <Money value={s.landed_cost_vnd} />
                </p>
              </div>
            </div>
          </CardLink>
        </li>
      ))}
    </ul>
  );
}

function DocsTab() {
  const { data, isPending, error } = useDocWarnings();
  const [upload, setUpload] = useState<{ po: string; kind: string } | null>(null);
  if (isPending) return <SkeletonList rows={2} />;
  if (error) return <EmptyState tone="error" title="Chưa tải được" description={error.message} />;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[14px] text-ink-2">
        Mỗi lô hàng đặt để bán cần hoá đơn mua và ảnh nhãn gốc (hộ kinh doanh, Luật Thương mại điện tử 2025). Tờ khai hải quan nên có nếu bên mua hộ cấp được.
      </p>
      {!data.length ? (
        <EmptyState icon={<Package />} title="Lô nào cũng đủ chứng từ" description="Khi có lô đặt hàng thiếu chứng từ, AI sẽ nhắc ở đây và ở màn hình Hôm nay." />
      ) : (
        <ul className="flex flex-col gap-2">
          {data.map((w) => (
            <li key={w.purchase_order_id} className="rounded-md border border-line border-l-[3px] border-l-review bg-surface p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <Link href={`/desk/nguon-cung/don/${w.purchase_order_id}`} className="text-[15px] font-semibold hover:underline">
                    {w.po_code}
                  </Link>
                  <p className="text-[14px] text-ink-2">{w.supplier_name ?? "—"}</p>
                  <p className="mt-1 text-[14px] text-review">Thiếu: {w.missing_labels.join(", ")}</p>
                </div>
                <POStatusBadge status={w.status} />
              </div>
              <Button size="sm" variant="secondary" className="mt-3" onClick={() => setUpload({ po: w.purchase_order_id, kind: w.missing[0] })}>
                Tải chứng từ
              </Button>
            </li>
          ))}
        </ul>
      )}
      <UploadSheet
        open={!!upload}
        onClose={() => setUpload(null)}
        purchaseOrderId={upload?.po}
        defaultKind={(upload?.kind as "invoice") ?? "invoice"}
      />
    </div>
  );
}
