/** Kỳ sổ sách: tháng `2026-11`, quý `2026-Q4`, năm `2026` — khớp `parse_period` của backend. */
export type PeriodOption = { value: string; label: string };

export function periodOptions(now = new Date()): PeriodOption[] {
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const months = Array.from({ length: 6 }, (_, i) => {
    const d = new Date(y, now.getMonth() - i, 1);
    const mm = d.getMonth() + 1;
    return { value: `${d.getFullYear()}-${String(mm).padStart(2, "0")}`, label: `${i === 0 ? "Tháng này · " : ""}Tháng ${mm}/${d.getFullYear()}` };
  });
  const q = Math.ceil(m / 3);
  const quarters = Array.from({ length: 4 }, (_, i) => {
    const idx = q - 1 - i;
    const qy = y + Math.floor(idx / 4);
    const qq = ((idx % 4) + 4) % 4 + 1;
    return { value: `${qy}-Q${qq}`, label: `Quý ${qq}/${qy}` };
  });
  return [...months, ...quarters, { value: String(y), label: `Năm ${y}` }, { value: String(y - 1), label: `Năm ${y - 1}` }];
}
