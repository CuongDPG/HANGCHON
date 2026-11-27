"use client";

import { CloudUpload, DatabaseBackup, Download, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  Card,
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
import { SettingsNav } from "@/components/control/settings-nav";
import { isOwner, useSession } from "@/lib/api/auth";
import { useSaveSettings } from "@/lib/api/control";
import { backupDownloadUrl, useBackupConfig, useBackups, useRunBackup, useVerifyBackup, type Backup, type BackupConfig } from "@/lib/api/finance";
import { cn } from "@/lib/cn";

function size(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

const STORAGE_LABELS: Record<string, string> = { local: "ổ đĩa máy chủ", s3: "kho đám mây (S3/R2)" };

/** Sao lưu CSDL (k4): lịch hằng ngày, giữ N bản, chép ra ngoài máy chủ, kiểm khôi phục, tải về. Chỉ chị. */
export function BackupScreen() {
  const { user } = useSession();
  const owner = isOwner(user);
  const cfg = useBackupConfig(owner);
  const list = useBackups(owner);
  const run = useRunBackup();
  const verify = useVerifyBackup();

  if (user && !owner) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader title="Sao lưu" />
        <SettingsNav />
        <EmptyState title="Chỉ chị (chủ cửa hàng) xem được phần này" />
      </div>
    );
  }

  async function backupNow() {
    const b = await run.mutateAsync();
    if (b.status !== "succeeded") notifyError(b.error ?? "Sao lưu lỗi.");
    else if (b.offsite_error) notifyError(`Đã sao lưu trên máy chủ nhưng chưa chép ra ngoài: ${b.offsite_error}`);
    else notifySuccess(`Đã sao lưu (${size(b.size_bytes)})${b.offsite_at ? ", đã chép ra ngoài máy chủ" : ""}`);
  }

  async function check(id: string) {
    const b = await verify.mutateAsync(id);
    if (b.verify_ok) notifySuccess("Bản sao lưu dùng được");
    else notifyError(b.verify_note ?? "Bản sao lưu có vấn đề.");
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Sao lưu"
        description="Sao lưu toàn bộ dữ liệu cửa hàng mỗi đêm. «Kiểm khôi phục» chỉ mở bản sao ra đọc thử, không ghi đè dữ liệu đang dùng."
        actions={
          <Button size="sm" icon={<DatabaseBackup className="size-4" />} loading={run.isPending} onClick={backupNow}>
            Sao lưu ngay
          </Button>
        }
      />
      <SettingsNav />

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

      {cfg.isPending ? <SkeletonList rows={1} /> : cfg.error ? <EmptyState tone="error" title="Chưa tải được" description={cfg.error.message} /> : <StatusCards cfg={cfg.data} />}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-[14px] text-ink-2">
          {cfg.data ? `${cfg.data.schedule} · giữ ${cfg.data.keep} bản gần nhất · lưu trên ${STORAGE_LABELS[cfg.data.storage_driver] ?? cfg.data.storage_driver}` : "…"}
        </p>
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
            <BackupRow key={b.id} b={b} checking={verify.isPending && verify.variables === b.id} onCheck={() => check(b.id)} />
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusCards({ cfg }: { cfg: BackupConfig }) {
  const offsiteOk = Boolean(cfg.offsite_driver && cfg.last_offsite_at && !cfg.offsite_error);
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <StatusCard
        icon={<ShieldCheck className={cn("size-5", cfg.last_success_at ? "text-auto" : "text-review")} aria-hidden />}
        label="Lần thành công gần nhất"
        value={cfg.last_success_at ? <DateTime value={cfg.last_success_at} format="dateTime" /> : "Chưa có"}
        note={cfg.last_success_at ? <DateTime value={cfg.last_success_at} format="relative" /> : "Bấm «Sao lưu ngay» để có bản đầu tiên."}
        tone={cfg.last_success_at ? "ok" : "warn"}
      />
      <StatusCard
        icon={<CloudUpload className={cn("size-5", offsiteOk ? "text-auto" : cfg.offsite_error ? "text-seal" : "text-review")} aria-hidden />}
        label="Bản ngoài máy chủ"
        value={!cfg.offsite_driver ? "Chưa bật" : cfg.last_offsite_at ? <DateTime value={cfg.last_offsite_at} format="dateTime" /> : "Chưa có bản nào"}
        note={
          cfg.offsite_error
            ? cfg.offsite_error
            : !cfg.offsite_driver
              ? "Bản sao chỉ nằm trên máy chủ, hỏng máy là mất cả bản sao. Nhờ người cài máy chủ điền kho S3/R2 (S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY)."
              : `Chép sang ${STORAGE_LABELS[cfg.offsite_driver] ?? cfg.offsite_driver} sau mỗi lần sao lưu.`
        }
        tone={cfg.offsite_error ? "error" : offsiteOk ? "ok" : "warn"}
      />
      <StatusCard
        icon={<TriangleAlert className={cn("size-5", cfg.last_error ? "text-seal" : "text-ink-3")} aria-hidden />}
        label="Lỗi gần nhất"
        value={cfg.last_error_at ? <DateTime value={cfg.last_error_at} format="dateTime" /> : "Không có"}
        note={cfg.last_error ?? "Từ lần thành công gần nhất chưa có lần nào lỗi."}
        tone={cfg.last_error ? "error" : "ok"}
      />
    </div>
  );
}

function StatusCard({ icon, label, value, note, tone }: { icon: ReactNode; label: string; value: ReactNode; note: ReactNode; tone: "ok" | "warn" | "error" }) {
  return (
    <Card tone={tone === "error" ? "danger" : tone === "warn" ? "accent" : "default"} className="flex min-w-0 flex-col gap-1">
      <p className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
        {icon}
        {label}
      </p>
      <p className="text-[17px] font-semibold">{value}</p>
      <p className={cn("text-[13px] [overflow-wrap:anywhere]", tone === "error" ? "text-seal" : "text-ink-2")}>{note}</p>
    </Card>
  );
}

function BackupRow({ b, checking, onCheck }: { b: Backup; checking: boolean; onCheck: () => void }) {
  const ok = b.status === "succeeded";
  return (
    <li className="flex flex-col gap-2 p-3.5 md:flex-row md:items-start md:justify-between md:gap-6">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[15px] font-semibold">
            <DateTime value={b.started_at} format="dateTime" />
          </p>
          <Badge tone={ok ? "success" : b.status === "failed" ? "danger" : "warning"}>{ok ? "Xong" : b.status === "failed" ? "Lỗi" : "Đang chạy"}</Badge>
          {ok && b.offsite_at ? <Badge tone="outline">Có bản ngoài máy chủ</Badge> : null}
          {ok && b.verified_at ? <Badge tone={b.verify_ok ? "success" : "danger"}>{b.verify_ok ? "Đã kiểm: dùng được" : "Đã kiểm: có vấn đề"}</Badge> : null}
        </div>
        <p className="text-[13px] text-ink-2">
          {b.trigger === "manual" ? "Chị bấm sao lưu" : "Theo lịch"} · {size(b.size_bytes)}
          {b.verified_at ? (
            <>
              {" "}
              · kiểm lúc <DateTime value={b.verified_at} format="dateTime" />
            </>
          ) : null}
        </p>
        {b.error ? <p className="text-[13px] text-seal [overflow-wrap:anywhere]">{b.error}</p> : null}
        {b.offsite_error ? <p className="text-[13px] text-seal [overflow-wrap:anywhere]">{b.offsite_error}</p> : null}
        {b.verify_note ? <p className={cn("text-[13px] [overflow-wrap:anywhere]", b.verify_ok ? "text-ink-2" : "text-seal")}>{b.verify_note}</p> : null}
      </div>
      {ok ? (
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button variant="secondary" size="sm" icon={<ShieldCheck className="size-4" />} loading={checking} onClick={onCheck}>
            Kiểm khôi phục
          </Button>
          <a href={backupDownloadUrl(b.id)} download className={buttonClasses({ variant: "ghost", size: "sm" })}>
            <Download className="size-4" aria-hidden /> Tải về (.sql.gz)
          </a>
        </div>
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
