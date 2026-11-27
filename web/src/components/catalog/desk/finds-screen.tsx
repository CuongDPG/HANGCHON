"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Search } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ProgressBar, SkeletonList } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { InlineSelect } from "@/components/ui/inline-select";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { notifySuccess } from "@/components/ui/toast";
import { useSession } from "@/lib/api/auth";
import { useDeskFinds, useDeskProducts, useFindAction, type DeskFindRequest, type FindStatus } from "@/lib/api/catalog";
import { api } from "@/lib/api/client";
import { DeskSubnav } from "./desk-subnav";

const SETTING = "catalog.find_request_threshold";

/** Nhờ tìm (e9): duyệt lời nhờ trước khi hiện, theo dõi số người cùng cần, chuyển trạng thái. */
export function FindsScreen() {
  const [tab, setTab] = useState<FindStatus>("pending_review");
  const { data, isPending, error } = useDeskFinds(tab);
  const rows = data?.items ?? [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Nhờ tìm" />
      <DeskSubnav active="finds" />
      <ThresholdSetting />
      <Tabs
        aria-label="Trạng thái"
        value={tab}
        onChange={setTab}
        items={[
          { value: "pending_review", label: "Chờ duyệt" },
          { value: "open", label: "Đang gom" },
          { value: "threshold_reached", label: "Đủ người" },
          { value: "searching", label: "Đang tìm" },
          { value: "found", label: "Đã có" },
          { value: "closed", label: "Chưa có món ưng" },
          { value: "rejected", label: "Không hiện" },
        ]}
      />
      {isPending ? (
        <SkeletonList rows={3} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<Search />} title="Không có lời nhờ nào ở mục này" />
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((r) => (
            <li key={r.id}>
              <FindCard r={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ThresholdSetting() {
  const qc = useQueryClient();
  const { user } = useSession();
  const settings = useQuery({
    queryKey: ["control", "settings"],
    queryFn: () => api.get<{ key: string; value: unknown }[]>("/api/desk/control/settings"),
  });
  const current = settings.data?.find((s) => s.key === SETTING)?.value;
  const [value, setValue] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (v: number) => api.patch(`/api/desk/control/settings/${SETTING}`, { value: v }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["control", "settings"] });
      setValue(null);
      notifySuccess("Đã đổi ngưỡng (áp cho lời nhờ mới)");
    },
  });
  if (user?.role !== "owner" || current === undefined) return null;
  const shown = value ?? String(current);
  return (
    <div className="flex items-end gap-2">
      <Input label="Ngưỡng mở tìm (người cùng cần)" inputMode="numeric" value={shown} onChange={(e) => setValue(e.target.value)} wrapperClassName="w-64" />
      {value !== null && value !== String(current) ? (
        <Button variant="secondary" loading={save.isPending} disabled={!(Number(value) >= 2)} onClick={() => save.mutate(Number(value))}>
          Lưu
        </Button>
      ) : null}
    </div>
  );
}

const NEXT: Partial<Record<FindStatus, { value: FindStatus; label: string }[]>> = {
  open: [{ value: "searching", label: "Bắt đầu tìm" }, { value: "closed", label: "Chưa có món ưng" }],
  threshold_reached: [{ value: "searching", label: "Bắt đầu tìm" }, { value: "closed", label: "Chưa có món ưng" }],
  searching: [{ value: "found", label: "Đã có trên kệ" }, { value: "closed", label: "Chưa có món ưng" }],
  closed: [{ value: "searching", label: "Tìm lại" }],
};

function FindCard({ r }: { r: DeskFindRequest }) {
  const { user } = useSession();
  const isOwner = user?.role === "owner";
  const act = useFindAction();
  const products = useDeskProducts({ status: "published" });
  const [picking, setPicking] = useState(false);
  const options = NEXT[r.status] ?? [];
  return (
    <Card className="flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-[15px] font-semibold">{r.title}</p>
        <Badge tone={r.status === "threshold_reached" ? "accent" : "outline"}>{r.public_status.label}</Badge>
      </div>
      {r.description ? <p className="text-[14px] text-ink-2">{r.description}</p> : null}
      <div className="flex items-center gap-3">
        <ProgressBar value={r.vote_count} max={r.vote_threshold} label={`${r.vote_count} trên ${r.vote_threshold} người`} className="flex-1" />
        <span className="text-[13px] tabular-nums text-ink-2">
          {r.vote_count}/{r.vote_threshold} người
        </span>
      </div>
      {r.contact ? <p className="text-[13px] text-ink-2">Liên hệ khách để lại: {r.contact}</p> : null}
      {r.moderation_note ? <p className="text-[13px] text-ink-3">AI: {r.moderation_note}</p> : null}
      {isOwner ? (
        <div className="flex flex-wrap items-center gap-2">
          {r.status === "pending_review" || r.status === "rejected" ? (
            <Button size="sm" icon={<Check className="size-4" />} loading={act.isPending} onClick={() => act.mutate({ id: r.id, status: "approve" }, { onSuccess: () => notifySuccess("Đã hiện lên bảng") })}>
              Hiện lên bảng
            </Button>
          ) : null}
          {r.status === "pending_review" ? (
            <Button size="sm" variant="ghost" onClick={() => act.mutate({ id: r.id, status: "rejected" })}>
              Không hiện
            </Button>
          ) : null}
          {options.map((o) =>
            o.value === "found" ? (
              <Button key={o.value} size="sm" variant="secondary" onClick={() => setPicking(true)}>
                {o.label}
              </Button>
            ) : (
              <Button key={o.value} size="sm" variant="secondary" loading={act.isPending && act.variables?.status === o.value}
                onClick={() => act.mutate({ id: r.id, status: o.value }, { onSuccess: () => notifySuccess("Đã cập nhật") })}>
                {o.label}
              </Button>
            ),
          )}
        </div>
      ) : null}
      {picking ? (
        <InlineSelect
          label="Món trên kệ đáp ứng yêu cầu này"
          placeholder="Chọn món"
          value={null}
          onChange={(pid) => act.mutate({ id: r.id, status: "found", productId: pid }, { onSuccess: () => { setPicking(false); notifySuccess("Đã báo: đã có trên kệ"); } })}
          options={(products.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }))}
        />
      ) : null}
    </Card>
  );
}
