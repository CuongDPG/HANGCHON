"use client";

import { RotateCw, TriangleAlert } from "lucide-react";
import { useState } from "react";
import {
  Button,
  Card,
  DataList,
  EmptyState,
  InlineSelect,
  Input,
  Money,
  PageHeader,
  ProgressBar,
  SectionLabel,
  SkeletonList,
  notifySuccess,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useAICosts, useSetBudget, type AICosts } from "@/lib/api/control";
import { formatNumber, formatVnd, formatVndCompact } from "@/lib/format";

function monthOptions(n = 6) {
  const now = new Date();
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    return { value: key, label: i === 0 ? `Tháng này (${d.getMonth() + 1}/${d.getFullYear()})` : `Tháng ${d.getMonth() + 1}/${d.getFullYear()}` };
  });
}

/** Chi phí AI theo tháng (k2): trần, cảnh báo, lịch sử theo ngày và theo tác vụ. */
export function AICostsScreen() {
  const months = monthOptions();
  const [month, setMonth] = useState(months[0].value);
  const { data, isPending, error, refetch } = useAICosts(month);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader backHref="/desk/tu-chu" title="Chi phí AI" description="Tiền gọi AI theo tháng. Chạm trần thì AI dừng và hỏi chị." />
      <InlineSelect aria-label="Tháng" value={month} onChange={setMonth} options={months} appearance="inline" className="self-start" />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được chi phí AI"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : (
        <CostBody data={data} current={month === months[0].value} />
      )}
    </div>
  );
}

function CostBody({ data, current }: { data: AICosts; current: boolean }) {
  const limited = data.budget_vnd > 0;
  const tone = data.used_pct >= 100 ? "danger" : data.used_pct >= 80 ? "warning" : "success";
  const maxDay = Math.max(1, ...data.by_day.map((d) => d.cost_vnd));
  return (
    <>
      <Card className="flex flex-col gap-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="font-display text-[30px] leading-none font-extrabold tabular-nums">{formatVndCompact(data.spent_vnd)}</p>
            <p className="mt-1 text-[13px] text-ink-2">đã dùng · {formatNumber(data.run_count)} lần gọi AI</p>
          </div>
          <p className="text-right text-[14px] text-ink-2">
            {limited ? (
              <>
                trần <b className="text-ink">{formatVndCompact(data.budget_vnd)}</b>
                <br />
                còn {formatVndCompact(data.remaining_vnd)}
              </>
            ) : (
              "Chưa đặt trần"
            )}
          </p>
        </div>
        {limited ? <ProgressBar value={data.spent_vnd} max={data.budget_vnd} tone={tone} label={`Đã dùng ${formatNumber(data.used_pct)}% trần`} /> : null}
        {limited && data.used_pct >= 80 ? (
          <p role="status" className="flex items-start gap-2 text-[14px] text-ink">
            <TriangleAlert className={tone === "danger" ? "mt-0.5 size-4 shrink-0 text-seal" : "mt-0.5 size-4 shrink-0 text-review"} aria-hidden />
            {data.used_pct >= 100
              ? "Đã chạm trần: AI dừng mọi việc và đang chờ chị quyết nâng trần (ở Chờ duyệt)."
              : `Đã dùng ${formatNumber(data.used_pct)}% trần. Chạm trần thì AI dừng và hỏi chị.`}
          </p>
        ) : null}
        {data.error_count || data.blocked_count ? (
          <p className="text-[13px] text-ink-2">
            {data.error_count ? `${data.error_count} lần lỗi` : ""}
            {data.error_count && data.blocked_count ? " · " : ""}
            {data.blocked_count ? `${data.blocked_count} lần bị chặn vì chạm trần` : ""}
          </p>
        ) : null}
      </Card>

      {current ? <BudgetForm budget={data.budget_vnd} /> : null}

      <section className="flex flex-col gap-2" aria-label="Theo ngày">
        <SectionLabel>Theo ngày</SectionLabel>
        {data.by_day.length ? (
          <Card>
            <div className="flex h-28 items-end gap-[3px]" role="img" aria-label={`Chi phí ${data.by_day.length} ngày có dùng AI`}>
              {data.by_day.map((d) => (
                <div
                  key={d.date}
                  title={`${d.date.slice(8, 10)}/${d.date.slice(5, 7)}: ${formatVnd(d.cost_vnd)}`}
                  className="min-w-0 flex-1 rounded-t-sm bg-accent"
                  style={{ height: `${Math.max(4, (d.cost_vnd / maxDay) * 100)}%` }}
                />
              ))}
            </div>
            <div className="mt-1.5 flex justify-between text-[12px] text-ink-3">
              <span>{data.by_day[0].date.slice(8, 10)}/{data.by_day[0].date.slice(5, 7)}</span>
              <span>{data.by_day.at(-1)!.date.slice(8, 10)}/{data.by_day.at(-1)!.date.slice(5, 7)}</span>
            </div>
          </Card>
        ) : (
          <p className="text-[14px] text-ink-2">Tháng này chưa gọi AI lần nào.</p>
        )}
      </section>

      <section className="flex flex-col gap-2" aria-label="Theo việc">
        <SectionLabel>Theo việc</SectionLabel>
        {data.by_task.length ? (
          <Card>
            <DataList
              items={data.by_task.map((t) => ({
                label: (
                  <span>
                    {t.label}
                    <span className="block text-[12px] text-ink-3">{formatNumber(t.runs)} lần</span>
                  </span>
                ),
                value: <Money value={t.cost_vnd} />,
              }))}
            />
          </Card>
        ) : (
          <p className="text-[14px] text-ink-2">Chưa có việc nào tốn tiền AI.</p>
        )}
      </section>
    </>
  );
}

function BudgetForm({ budget }: { budget: number }) {
  const { user } = useSession();
  const [value, setValue] = useState(budget ? String(budget) : "");
  const save = useSetBudget();
  if (!isOwner(user)) return null;
  const n = Number(value.replace(/\D/g, "") || 0);
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        await save.mutateAsync(n);
        notifySuccess(n ? `Đã đặt trần ${formatVnd(n)} mỗi tháng` : "Đã bỏ trần chi phí AI");
      }}
    >
      <div className="flex items-end gap-2">
        <Input
          label="Trần mỗi tháng"
          inputMode="numeric"
          value={value ? formatNumber(n) : ""}
          onChange={(e) => setValue(e.target.value)}
          trailing="đ"
          hint="Để 0 nếu không muốn giới hạn."
          wrapperClassName="flex-1"
        />
        <Button type="submit" loading={save.isPending} disabled={n === budget} className="mb-[26px]">
          Lưu
        </Button>
      </div>
    </form>
  );
}
