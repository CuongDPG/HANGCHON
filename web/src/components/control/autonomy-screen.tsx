"use client";

import { Lightbulb, RotateCw } from "lucide-react";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardLink,
  EmptyState,
  LevelTag,
  PageHeader,
  ProgressBar,
  SectionLabel,
  Segmented,
  Skeleton,
  SkeletonList,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useAICosts, useAutonomy, useSetAutonomy, type AutonomyRow } from "@/lib/api/control";
import { formatNumber, formatVndCompact } from "@/lib/format";

type Settable = "auto" | "ask" | "off";

const OPTIONS: { value: Settable; label: string }[] = [
  { value: "auto", label: "Tự làm" },
  { value: "ask", label: "Hỏi chị" },
  { value: "off", label: "Tắt" },
];

/** «AI được tự làm tới đâu» (i3) + thẻ trần chi phí AI (k2). */
export function AutonomyScreen() {
  const { data, isPending, error, refetch } = useAutonomy();
  const { user } = useSession();
  const owner = isOwner(user);
  const set = useSetAutonomy();
  const confirm = useConfirm();
  const [dismissed, setDismissed] = useState<string[]>([]);

  async function change(row: AutonomyRow, level: Settable) {
    if (level === row.level) return;
    if (level === "auto" && row.customer_facing) {
      const ok = await confirm({
        title: `Cho AI tự làm «${row.label}»?`,
        message: "Việc này khách nhìn thấy. Từ giờ AI làm luôn, không chờ chị xem trước; chị vẫn xem lại và hoàn tác được trong Nhật ký AI.",
        confirmLabel: "Cho tự làm",
      });
      if (!ok) return;
    }
    await set.mutateAsync({ action: row.action, level });
    notifySuccess(`«${row.label}»: ${OPTIONS.find((o) => o.value === level)?.label}`);
  }

  const rows = data ?? [];
  const free = rows.filter((r) => !r.locked);
  const locked = rows.filter((r) => r.locked);
  const groups = [...new Set(free.map((r) => r.group))].sort((a, b) => a.localeCompare(b, "vi"));
  const suggestions = free.filter((r) => r.suggest_auto && !dismissed.includes(r.action));

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Mức tự chủ của AI" description="Mặc định là thận trọng: việc nội bộ AI tự làm, thứ khách nhìn thấy thì hỏi chị trước." />

      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được bảng mức tự chủ"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : rows.length === 0 ? (
        <EmptyState title="Chưa có việc nào để đặt mức" description="Các khu (săn hàng, nội dung, đơn hàng…) sẽ tự thêm việc vào đây." />
      ) : (
        <>
          {suggestions.map((r) => (
            <Card key={r.action} tone="accent" className="flex flex-col gap-3">
              <div className="flex items-start gap-3">
                <Lightbulb className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
                <p className="text-[15px]">
                  Chị đã duyệt <b>«{r.label}»</b> {r.history.streak} lần liền mà không sửa. Cho AI tự làm việc này?
                </p>
              </div>
              {owner ? (
                <div className="flex gap-2 max-md:[&>*]:flex-1">
                  <Button size="sm" variant="secondary" onClick={() => setDismissed((d) => [...d, r.action])}>
                    Để sau
                  </Button>
                  <Button size="sm" onClick={() => change(r, "auto")}>
                    Cho tự làm
                  </Button>
                </div>
              ) : null}
            </Card>
          ))}

          {!owner ? <p className="text-[14px] text-ink-2">Chỉ chị (chủ cửa hàng) đổi được mức tự chủ.</p> : null}

          {groups.map((g) => (
            <section key={g} className="flex flex-col gap-3" aria-label={g}>
              <SectionLabel>{g}</SectionLabel>
              <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
                {free
                  .filter((r) => r.group === g)
                  .map((r) => (
                    <li key={r.action} className="flex flex-col gap-2 p-3.5 md:flex-row md:items-center md:justify-between">
                      <div className="min-w-0">
                        <p className="text-[15px] font-semibold">{r.label}</p>
                        <p className="text-[13px] text-ink-2">
                          {r.customer_facing ? "Khách nhìn thấy" : "Việc nội bộ"}
                          {historyText(r.history)}
                        </p>
                      </div>
                      <Segmented<Settable>
                        aria-label={`Mức tự chủ: ${r.label}`}
                        value={r.level as Settable}
                        onChange={(v) => change(r, v)}
                        options={OPTIONS.map((o) => ({ ...o, disabled: !owner }))}
                        size="sm"
                        className="self-start md:self-auto"
                      />
                    </li>
                  ))}
              </ul>
            </section>
          ))}

          {locked.length ? (
            <section className="flex flex-col gap-3" aria-label="Luôn hỏi chị">
              <SectionLabel>Luôn hỏi chị</SectionLabel>
              <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
                {locked.map((r) => (
                  <li key={r.action} className="flex items-center justify-between gap-3 p-3.5">
                    <p className="min-w-0 text-[15px] font-semibold">{r.label}</p>
                    <LevelTag level="owner" size="sm">
                      Luôn hỏi chị
                    </LevelTag>
                  </li>
                ))}
              </ul>
              <p className="text-[13px] text-ink-2">Những việc này khoá cứng: AI chỉ chuẩn bị phương án, chị quyết.</p>
            </section>
          ) : null}
        </>
      )}

      <AICostCard />
    </div>
  );
}

function historyText(h: AutonomyRow["history"]): string {
  const parts = [
    h.approved ? `duyệt ${h.approved}` : "",
    h.edited ? `có sửa ${h.edited}` : "",
    h.returned ? `trả lại ${h.returned}` : "",
  ].filter(Boolean);
  return parts.length ? ` · gần đây ${parts.join(", ")}` : "";
}

/** Thẻ chi phí AI tháng này (k2), bấm vào xem chi tiết và đặt trần. */
export function AICostCard() {
  const { data, isPending } = useAICosts();
  if (isPending) return <Skeleton className="h-24 w-full" />;
  if (!data) return null;
  const limited = data.budget_vnd > 0;
  const tone = data.used_pct >= 100 ? "danger" : data.used_pct >= 80 ? "warning" : "success";
  return (
    <CardLink href="/desk/tu-chu/chi-phi-ai" tone="soft" className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[15px] font-semibold">
          {limited ? `Trần chi phí AI: ${formatVndCompact(data.budget_vnd)} mỗi tháng` : "Chi phí AI: chưa đặt trần"}
        </p>
        {limited && data.used_pct >= 80 ? <Badge tone={tone === "danger" ? "danger" : "warning"}>{formatNumber(data.used_pct)}%</Badge> : null}
      </div>
      {limited ? <ProgressBar value={data.spent_vnd} max={data.budget_vnd} tone={tone} size="sm" label="Đã dùng so với trần" /> : null}
      <p className="text-[14px] text-ink-2">
        Tháng này đã dùng {formatVndCompact(data.spent_vnd)}. {limited ? "Chạm trần thì AI dừng và hỏi chị." : ""}{" "}
        <span className="font-semibold text-accent">Chi tiết →</span>
      </p>
    </CardLink>
  );
}
