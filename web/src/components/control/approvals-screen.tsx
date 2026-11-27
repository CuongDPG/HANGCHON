"use client";

import { CheckCheck, ClipboardCheck, RotateCw } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import {
  Button,
  Chip,
  ChipRow,
  EmptyState,
  PageHeader,
  SkeletonList,
  Tabs,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useApprovalGroups, useApprovals, useApproveBatch, type ApprovalItem } from "@/lib/api/control";
import { ApprovalRow } from "./approval-row";
import { ApprovalSheet } from "./approval-sheet";

type Tab = "pending" | "done";

/** Hàng chờ duyệt (i2): lọc theo loại việc, duyệt hàng loạt các việc cùng loại, xem lại việc đã xử lý. */
export function ApprovalsScreen() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>("pending");
  const [action, setAction] = useState<string | undefined>(params.get("action") ?? undefined);
  const [open, setOpen] = useState<ApprovalItem | null>(null);
  const [openId, setOpenId] = useState<string | null>(params.get("id"));
  const { user } = useSession();
  const confirm = useConfirm();
  const groups = useApprovalGroups();
  const list = useApprovals(
    tab === "pending" ? { action } : { action, status: ["approved", "returned", "failed", "cancelled", "expired"] },
  );
  const batch = useApproveBatch();
  const totalPending = groups.data?.reduce((n, g) => n + g.count, 0);
  const group = groups.data?.find((g) => g.action === action);
  const items = list.data?.items ?? [];
  const canBatch = isOwner(user) && tab === "pending" && group && !group.locked && items.length >= 2;

  async function approveAll() {
    if (!group) return;
    const ok = await confirm({
      title: `Duyệt cả ${items.length} việc?`,
      message: `Tất cả việc «${group.label}» đang chờ sẽ được thực hiện ngay. Chị đã xem qua phần xem trước chưa?`,
      confirmLabel: `Duyệt ${items.length} việc`,
    });
    if (!ok) return;
    const res = await batch.mutateAsync(items.map((i) => i.id));
    if (res.failed) notifyError(`Đã duyệt ${res.approved} việc, ${res.failed} việc lỗi — mở từng việc để xem.`);
    else notifySuccess(`Đã duyệt ${res.approved} việc`);
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Chờ duyệt" />
      <Tabs
        aria-label="Trạng thái"
        value={tab}
        onChange={setTab}
        items={[
          { value: "pending", label: "Đang chờ", count: totalPending },
          { value: "done", label: "Đã xử lý" },
        ]}
      />
      {groups.data && groups.data.length > 1 && tab === "pending" ? (
        <ChipRow>
          <Chip selected={!action} count={totalPending} onClick={() => setAction(undefined)}>
            Tất cả
          </Chip>
          {groups.data.map((g) => (
            <Chip key={g.action} selected={action === g.action} count={g.count} onClick={() => setAction(g.action)}>
              {g.label}
            </Chip>
          ))}
        </ChipRow>
      ) : null}

      {canBatch ? (
        <Button variant="secondary" icon={<CheckCheck className="size-4" />} loading={batch.isPending} onClick={approveAll} className="self-start">
          Duyệt cả {items.length} việc «{group.label}»
        </Button>
      ) : null}

      {list.isPending ? (
        <SkeletonList rows={4} />
      ) : list.error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được hàng chờ"
          description={list.error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => list.refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck />}
          title={tab === "pending" ? "Không có việc nào đang chờ" : "Chưa có việc nào đã xử lý"}
          description={tab === "pending" ? "Khi AI làm xong một việc cần chị gật, việc đó sẽ hiện ở đây." : undefined}
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((it) => (
            <li key={it.id}>
              <ApprovalRow item={it} onOpen={setOpen} />
            </li>
          ))}
        </ul>
      )}
      {list.data && list.data.total > items.length ? (
        <p className="text-[13px] text-ink-2">Đang hiện {items.length} trên {list.data.total} việc. Xử lý bớt để xem tiếp.</p>
      ) : null}

      <ApprovalSheet
        item={open}
        itemId={open ? null : openId}
        open={!!open || !!openId}
        onClose={() => {
          setOpen(null);
          setOpenId(null);
        }}
      />
    </div>
  );
}
