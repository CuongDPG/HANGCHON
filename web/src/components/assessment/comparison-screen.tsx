"use client";

import Link from "next/link";
import { Badge, Button, Card, EmptyState, PageHeader, Skeleton, SkeletonList } from "@/components/ui";
import { CandidateThumb } from "@/components/sourcing/supplier-gallery";
import { useComparison } from "@/lib/api/assessment";
import { cn } from "@/lib/cn";

/** b3 — Bảng so sánh cạnh nhau: 2–5 ứng viên cùng đề theo tiêu chí, ô tốt nhất tô chàm. */
export function ComparisonScreen({ id }: { id: string }) {
  const { data, isPending, error, refetch } = useComparison(id);
  if (isPending)
    return (
      <div className="flex flex-col gap-4" role="status" aria-label="Đang tải">
        <Skeleton className="h-8 w-56" />
        <SkeletonList rows={5} />
      </div>
    );
  if (error || !data)
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="So sánh" backHref="/desk/san-hang" />
        <EmptyState
          tone="error"
          title="Chưa tải được bảng so sánh"
          description={error?.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      </div>
    );
  const cands = new Map(data.candidates.map((c) => [c.id, c]));
  return (
    <div className="flex flex-col gap-4">
      <PageHeader backHref={data.brief_id ? `/desk/san-hang/de/${data.brief_id}` : "/desk/san-hang"} title="So sánh cạnh nhau" description={data.title} />
      {data.conclusion ? (
        <Card tone="soft">
          <p className="text-[15px] [text-wrap:pretty]">{data.conclusion}</p>
        </Card>
      ) : null}
      <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <table className="w-full min-w-[34rem] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-[1] w-28 bg-paper p-2 text-left align-bottom font-medium text-ink-2">
                Tiêu chí
              </th>
              {data.items.map((it) => {
                const c = cands.get(it.candidate_id);
                const rec = data.recommended_candidate_id === it.candidate_id;
                return (
                  <th key={it.id} scope="col" className="min-w-36 p-2 text-left align-top font-normal">
                    <CandidateThumb candidateId={it.candidate_id} src={c?.thumb_url ?? null} count={c?.image_count ?? 0} title={c?.title_vi ?? "Ứng viên"} className="mb-1.5 w-20" />
                    <Link href={`/desk/san-hang/ung-vien/${it.candidate_id}`} className="flex flex-col gap-1.5">
                      <span className="text-[13px] leading-snug font-semibold [text-wrap:pretty]">{c?.title_vi}</span>
                      {rec ? <Badge tone="accent">Nên mua mẫu</Badge> : null}
                    </Link>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {data.criteria.map((k) => (
              <tr key={k.key}>
                <th scope="row" className="sticky left-0 z-[1] border-t border-line bg-paper p-2 text-left align-top font-normal text-ink-2">
                  {k.label}
                </th>
                {data.items.map((it) => {
                  const cell = it.values[k.key];
                  return (
                    <td
                      key={it.id}
                      className={cn("border-t border-line p-2 align-top tabular-nums", cell?.best && "bg-accent-wash font-semibold text-accent")}
                      title={cell?.note ?? undefined}
                    >
                      {cell?.value ?? "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12.5px] text-ink-3">Ô tô chàm là tốt nhất ở tiêu chí đó. Món chưa thẩm định thì chưa có điểm từng tiêu chí.</p>
    </div>
  );
}
