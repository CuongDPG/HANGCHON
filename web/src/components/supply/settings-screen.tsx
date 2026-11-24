"use client";

import { useState } from "react";
import { Button, Card, EmptyState, Input, PageHeader, SectionLabel, SkeletonList, notifySuccess } from "@/components/ui";
import { num, useCostParams, useSaveCostParams, type CostParams } from "@/lib/api/supply";

/** Tham số mặc định tính giá vốn về tay (d2). Đổi thì các bảng giá vốn «tự cập nhật» được tính lại. */
export function CostSettingsScreen() {
  const { data, isPending, error } = useCostParams();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Tham số giá vốn"
        description="Tỷ giá, cước, phí và thuế mặc định. Đổi xong, các món đang tự cập nhật sẽ được tính lại."
        backHref="/desk/nguon-cung?tab=gia-von"
      />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : (
        <ParamsForm initial={data} />
      )}
    </div>
  );
}

function ParamsForm({ initial }: { initial: CostParams }) {
  const save = useSaveCostParams();
  const [v, setV] = useState(() => ({
    CNY: String(num(initial.fx_rates.CNY)),
    JPY: String(num(initial.fx_rates.JPY)),
    USD: String(num(initial.fx_rates.USD)),
    CN: String(initial.intl_vnd_per_kg.CN ?? 0),
    JP: String(initial.intl_vnd_per_kg.JP ?? 0),
    agent_fee_pct: String(num(initial.agent_fee_pct)),
    domestic_shipping_vnd: String(initial.domestic_shipping_vnd),
    packaging_vnd: String(initial.packaging_vnd),
    import_tax_pct: String(num(initial.import_tax_pct)),
    vat_pct: String(num(initial.vat_pct)),
    loss_pct: String(num(initial.loss_pct)),
    target_margin_pct: String(num(initial.target_margin_pct)),
  }));
  const field = (k: keyof typeof v, label: string, trailing: string, hint?: string) => (
    <Input label={label} inputMode="decimal" value={v[k]} onChange={(e) => setV((x) => ({ ...x, [k]: e.target.value }))} trailing={trailing} hint={hint} />
  );
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        const r = await save.mutateAsync({
          fx_rates: { CNY: v.CNY, JPY: v.JPY, USD: v.USD },
          intl_vnd_per_kg: { CN: Math.round(Number(v.CN)), JP: Math.round(Number(v.JP)) },
          agent_fee_pct: v.agent_fee_pct,
          domestic_shipping_vnd: Math.round(Number(v.domestic_shipping_vnd)),
          packaging_vnd: Math.round(Number(v.packaging_vnd)),
          import_tax_pct: v.import_tax_pct,
          vat_pct: v.vat_pct,
          loss_pct: v.loss_pct,
          target_margin_pct: v.target_margin_pct,
        });
        notifySuccess(r.recalculated ? `Đã lưu, tính lại ${r.recalculated} món` : "Đã lưu tham số");
      }}
    >
      <Card className="flex flex-col gap-3">
        <SectionLabel>Tỷ giá (VND cho 1 đơn vị)</SectionLabel>
        <div className="grid grid-cols-3 gap-3">
          {field("CNY", "Nhân dân tệ", "đ")}
          {field("JPY", "Yên Nhật", "đ")}
          {field("USD", "Đô la Mỹ", "đ")}
        </div>
      </Card>
      <Card className="flex flex-col gap-3">
        <SectionLabel>Cước và phí</SectionLabel>
        <div className="grid grid-cols-2 gap-3">
          {field("CN", "Cước từ Trung Quốc", "đ/kg", "Đường bộ, tiểu ngạch: xin báo giá 3–5 nơi")}
          {field("JP", "Cước từ Nhật", "đ/kg", "Gom hàng đường bay")}
          {field("agent_fee_pct", "Phí mua hộ", "%")}
          {field("domestic_shipping_vnd", "Cước nội địa mỗi cái", "đ")}
          {field("packaging_vnd", "Đóng gói mỗi cái", "đ")}
          {field("loss_pct", "Hao hụt, đổi trả", "%")}
        </div>
      </Card>
      <Card className="flex flex-col gap-3">
        <SectionLabel>Thuế và biên lợi nhuận</SectionLabel>
        <div className="grid grid-cols-2 gap-3">
          {field("import_tax_pct", "Thuế nhập khẩu", "%", "Theo mã HS; cần kế toán xác nhận")}
          {field("vat_pct", "Thuế GTGT", "%", "Hàng giá trị nhỏ không còn miễn từ 18/02/2025")}
          {field("target_margin_pct", "Biên mục tiêu", "%", "Dùng khi AI đề xuất giá bán")}
        </div>
      </Card>
      <Button type="submit" loading={save.isPending} className="self-end">
        Lưu và tính lại
      </Button>
    </form>
  );
}
