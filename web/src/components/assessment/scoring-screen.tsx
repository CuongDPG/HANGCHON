"use client";

import { useState } from "react";
import { Badge, Button, Card, CardHeader, EmptyState, Input, PageHeader, SkeletonList, notifyError, notifySuccess } from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { usePatchProfile, useScoringProfiles, type Criterion, type ScoringProfile } from "@/lib/api/assessment";

function ProfileEditor({ p, canEdit }: { p: ScoringProfile; canEdit: boolean }) {
  const [rows, setRows] = useState<Criterion[]>(p.criteria);
  const [pass, setPass] = useState(String(p.pass_score ?? ""));
  const save = usePatchProfile();
  const sum = rows.reduce((s, r) => s + (Number(r.weight) || 0), 0);
  const dirty = JSON.stringify(rows) !== JSON.stringify(p.criteria) || pass !== String(p.pass_score ?? "");
  return (
    <Card className="flex flex-col gap-3">
      <CardHeader title={p.name} aside={p.is_default ? <Badge tone="accent">Dùng chung</Badge> : <Badge>Theo nhóm hàng</Badge>} />
      <ul className="flex flex-col gap-2">
        {rows.map((r, i) => (
          <li key={r.key} className="grid grid-cols-[1fr_5.5rem] items-end gap-2">
            <div className="min-w-0">
              <p className="text-[15px] font-medium">{r.label}</p>
              {r.description ? <p className="text-[12.5px] text-ink-2">{r.description}</p> : null}
            </div>
            <Input
              aria-label={`Trọng số ${r.label}`}
              inputMode="numeric"
              trailing="đ"
              value={String(r.weight)}
              disabled={!canEdit}
              onChange={(e) => {
                const w = Number(e.target.value.replace(/[^\d.]/g, "")) || 0;
                setRows((cur) => cur.map((x, j) => (j === i ? { ...x, weight: w } : x)));
              }}
            />
          </li>
        ))}
      </ul>
      <p className={`text-sm font-medium ${sum === 100 ? "text-auto" : "text-seal"}`}>
        Tổng trọng số: {sum}/100{sum !== 100 ? " — cần đúng 100" : ""}
      </p>
      <Input
        label="Ngưỡng điểm để vào bảng chọn"
        inputMode="numeric"
        value={pass}
        disabled={!canEdit}
        onChange={(e) => setPass(e.target.value.replace(/\D/g, ""))}
      />
      {canEdit ? (
        <Button
          className="self-end"
          disabled={!dirty || sum !== 100}
          loading={save.isPending}
          onClick={() =>
            save.mutate(
              { id: p.id, criteria: rows, pass_score: pass ? Number(pass) : null },
              { onSuccess: () => notifySuccess("Đã lưu khung chấm"), onError: notifyError },
            )
          }
        >
          Lưu khung chấm
        </Button>
      ) : null}
    </Card>
  );
}

/** b4 — Khung chấm điểm của chị: 7 tiêu chí, trọng số (đ) cộng lại bằng 100. Chỉ chị sửa được. */
export function ScoringScreen() {
  const { data, isPending, error } = useScoringProfiles();
  const session = useSession();
  const canEdit = session.user?.role === "owner";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader backHref="/desk/san-hang" title="Khung chấm điểm" />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được khung chấm" description={error.message} />
      ) : (
        data.map((p) => <ProfileEditor key={`${p.id}-${p.updated_at ?? ""}`} p={p} canEdit={canEdit} />)
      )}
    </div>
  );
}
