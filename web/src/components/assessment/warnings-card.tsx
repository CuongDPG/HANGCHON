"use client";

import { AlertOctagon, AlertTriangle, Check, Info } from "lucide-react";
import { Badge, Button, Card, CardHeader, notifyError, notifySuccess } from "@/components/ui";
import { useConfirmSafety, type Assessment, type Level } from "@/lib/api/assessment";

const ICON: Record<Level, typeof Info> = { info: Info, warning: AlertTriangle, danger: AlertOctagon };
const COLOR: Record<Level, string> = { info: "text-ink-2", warning: "text-review", danger: "text-seal" };
const SAFETY: Record<string, { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  ok: { label: "An toàn: ổn", tone: "success" },
  warning: { label: "An toàn: cần lưu ý", tone: "warning" },
  blocked: { label: "Chưa bán được", tone: "danger" },
  unchecked: { label: "Chưa soát an toàn", tone: "neutral" },
};

/** «Cần chị để ý»: an toàn + giấy tờ (b6), hàng nhái / đánh giá ảo (b7), chỗ AI chưa chắc. */
export function WarningsCard({
  warnings,
  a,
  candidateId,
  canEdit,
}: {
  warnings: { level: Level; kind: string; text: string }[];
  a: Assessment | null;
  candidateId: string;
  canEdit: boolean;
}) {
  const confirm = useConfirmSafety(candidateId, a?.id ?? "");
  const safety = a ? SAFETY[a.safety_status] : null;
  const docs = a?.safety.docs_needed ?? [];
  return (
    <Card tone={warnings.some((w) => w.level === "danger") ? "danger" : "accent"} className="flex flex-col gap-2">
      <CardHeader title="Cần chị để ý" aside={safety ? <Badge tone={safety.tone}>{safety.label}</Badge> : null} />
      {warnings.length ? (
        <ul className="flex flex-col gap-1.5">
          {warnings.map((w, i) => {
            const Icon = ICON[w.level];
            return (
              <li key={`${w.kind}-${i}`} className="flex items-start gap-2 text-sm">
                <Icon className={`mt-0.5 size-4 shrink-0 ${COLOR[w.level]}`} aria-hidden />
                <span className="[text-wrap:pretty]">{w.text}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-ink-2">Chưa thấy điều gì cần lưu ý.</p>
      )}
      {docs.length ? (
        <p className="text-[13px] text-ink-2">
          <span className="font-medium text-ink">Giấy tờ nên có:</span> {docs.join("; ")}
        </p>
      ) : null}
      {a && a.safety_status !== "unchecked" ? (
        a.safety_confirmed_at ? (
          <p className="flex items-center gap-1.5 text-[13px] text-auto">
            <Check className="size-3.5" aria-hidden /> Chị đã xem phần an toàn
          </p>
        ) : canEdit ? (
          <Button
            size="sm"
            variant="secondary"
            className="self-start"
            loading={confirm.isPending}
            onClick={() => confirm.mutate({}, { onSuccess: () => notifySuccess("Đã ghi nhận"), onError: notifyError })}
          >
            Đã xem phần an toàn
          </Button>
        ) : null
      ) : null}
    </Card>
  );
}
