"use client";

import { DatabaseBackup, Download, TriangleAlert } from "lucide-react";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  DataList,
  DateTime,
  EmptyState,
  Input,
  PageHeader,
  SectionLabel,
  SkeletonList,
  buttonClasses,
  notifyError,
  notifySuccess,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { useSaveSettings } from "@/lib/api/control";
import { backupDownloadUrl, useBackupConfig, useBackups, useRunBackup, type Backup } from "@/lib/api/finance";

function size(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

/** Sao lưu CSDL (k4): lịch hằng ngày, giữ N bản, sao lưu ngay, tải về. Chỉ chị. */
export function BackupScreen() {
  const { user } = useSession();
  const owner = isOwner(user);
  const cfg = useBackupConfig(owner);
  const list = useBackups(owner);
  const run = useRunBackup();

  if (user && !owner) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader backHref="/desk/cai-dat" title="Sao lưu" />
        <EmptyState title="Chỉ chị (chủ cửa hàng) xem được phần này" />
      </div>
    );
  }

  async function backupNow() {
    const b = await run.mutateAsync();
    if (b.status === "succeeded") notifySuccess(`Đã sao lưu (${size(b.size_bytes)})`);
    else notifyError(b.error ?? "Sao lưu lỗi.");
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader backHref="/desk/cai-dat" title="Sao lưu" description="Sao lưu toàn bộ dữ liệu cửa hàng. Bản sao nén lưu trong kho tệp riêng tư." />

      {cfg.data && !cfg.data.pg_dump ? (
        <Card tone="danger" className="flex items-start gap-3">
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-seal" aria-hidden />
          <div className="text-[14px]">
            <p className="font-semibold">Máy chủ chưa có công cụ sao lưu (pg_dump)</p>
            <p className="text-ink-2">
              Cài gói <code>postgresql-client</code> cùng bản với Postgres trên máy chạy API, hoặc đặt <code>PG_DUMP_PATH</code>. Chưa cài thì
              bản sao lưu hằng ngày sẽ báo lỗi.
            </p>
          </div>
        </Card>
      ) : null}

      <Card flush className="px-4 py-2">
        <DataList
          items={[
            { label: "Lịch", value: cfg.data?.schedule ?? "…" },
            { label: "Giữ lại", value: cfg.data ? `${cfg.data.keep} bản gần nhất` : "…" },
            { label: "Lần thành công gần nhất", value: cfg.data?.last_success_at ? <DateTime value={cfg.data.last_success_at} format="relative" /> : "Chưa có" },
          ]}
        />
      </Card>

      <div className="flex flex-wrap items-end gap-3">
        <Button icon={<DatabaseBackup className="size-4" />} loading={run.isPending} onClick={backupNow}>
          Sao lưu ngay
        </Button>
        {cfg.data ? <KeepForm key={cfg.data.keep} keep={cfg.data.keep} /> : null}
      </div>

      <SectionLabel>Các bản sao lưu</SectionLabel>
      {list.isPending ? (
        <SkeletonList rows={3} />
      ) : list.error ? (
        <EmptyState tone="error" title="Chưa tải được" description={list.error.message} />
      ) : !list.data.items.length ? (
        <EmptyState icon={<DatabaseBackup />} title="Chưa có bản sao lưu nào" description="Bản đầu tiên tự chạy lúc 3:15 sáng mai, hoặc bấm Sao lưu ngay." />
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {list.data.items.map((b) => (
            <BackupRow key={b.id} b={b} />
          ))}
        </ul>
      )}
    </div>
  );
}

function BackupRow({ b }: { b: Backup }) {
  const ok = b.status === "succeeded";
  return (
    <li className="flex flex-col gap-1 p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold">
            <DateTime value={b.started_at} format="dateTime" />
          </p>
          <p className="text-[13px] text-ink-2">
            {b.trigger === "manual" ? "Chị bấm sao lưu" : "Theo lịch"} · {size(b.size_bytes)}
          </p>
        </div>
        <Badge tone={ok ? "success" : b.status === "failed" ? "danger" : "warning"}>
          {ok ? "Xong" : b.status === "failed" ? "Lỗi" : "Đang chạy"}
        </Badge>
      </div>
      {b.error ? <p className="text-[13px] text-seal [overflow-wrap:anywhere]">{b.error}</p> : null}
      {ok ? (
        <a href={backupDownloadUrl(b.id)} download className={buttonClasses({ variant: "ghost", size: "sm", className: "-ml-3 self-start" })}>
          <Download className="size-4" aria-hidden /> Tải về (.sql.gz)
        </a>
      ) : null}
    </li>
  );
}

function KeepForm({ keep }: { keep: number }) {
  const [v, setV] = useState(String(keep));
  const save = useSaveSettings();
  const n = Number(v);
  return (
    <form
      className="flex items-end gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        await save.mutateAsync({ "finance.backup_keep": n });
        notifySuccess(`Giữ ${n} bản gần nhất`);
      }}
    >
      <Input label="Giữ lại" inputMode="numeric" value={v} onChange={(e) => setV(e.target.value.replace(/\D/g, ""))} trailing="bản" wrapperClassName="w-28" />
      <Button type="submit" variant="secondary" disabled={!n || n === keep} loading={save.isPending}>
        Lưu
      </Button>
    </form>
  );
}
