"use client";

import { ChevronDown, History, RotateCcw, RotateCw, ShieldCheck } from "lucide-react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import {
  Badge,
  Button,
  Chip,
  DateTime,
  EmptyState,
  InlineSelect,
  LevelTag,
  PageHeader,
  SkeletonList,
  Toolbar,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import { moduleLabel, useActivity, useAudit, useAutonomy, useUndo, type Activity, type AuditEntry } from "@/lib/api/control";
import { formatDate, formatWeekday } from "@/lib/format";
import { AI_LOG_SECTIONS } from "@/lib/desk-sections";
import { useUrlParam } from "@/lib/use-url-param";
import { Rationale } from "./preview-view";

type Range = "hom-nay" | "7-ngay" | "30-ngay" | "tat-ca";

const RANGES: { value: Range; label: string; days: number | null }[] = [
  { value: "hom-nay", label: "Hôm nay", days: 0 },
  { value: "7-ngay", label: "7 ngày", days: 6 },
  { value: "30-ngay", label: "30 ngày", days: 29 },
  { value: "tat-ca", label: "Tất cả", days: null },
];

/** Ngày theo giờ Việt Nam dạng YYYY-MM-DD. */
function vnDate(offsetDays = 0): string {
  const d = new Date(Date.now() - offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(d);
}

/** Nhật ký AI (i4) + lưu vết duyệt (k3). */
export function ActivityScreen() {
  const tab = useSearchParams().get("tab") === "luu-vet" ? "audit" : "ai";
  const { user } = useSession();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={AI_LOG_SECTIONS} active={tab} />
      {tab === "ai" ? (
        <AILog />
      ) : isOwner(user) ? (
        <AuditLog />
      ) : (
        <EmptyState icon={<ShieldCheck />} title="Chỉ chị xem được lưu vết" description="Lưu vết ghi mọi lần duyệt, đổi mức tự chủ và đổi cài đặt." />
      )}
    </div>
  );
}

function AILog() {
  const [range, setRange] = useUrlParam<Range>("ngay", "7-ngay", RANGES.map((r) => r.value));
  const [module, setModule] = useUrlParam<string>("khu", "all");
  const [actionParam, setActionParam] = useUrlParam<string>("action", "");
  const action = actionParam || undefined;
  const setAction = (a?: string) => setActionParam(a ?? "");
  const [page, setPage] = useState(1);
  const days = RANGES.find((r) => r.value === range)?.days;
  const autonomy = useAutonomy();
  const modules = [...new Set((autonomy.data ?? []).map((a) => a.module))];
  const actionLabel = autonomy.data?.find((a) => a.action === action)?.label ?? action;
  const q = {
    date_from: days === null || days === undefined ? undefined : vnDate(days),
    date_to: days === null || days === undefined ? undefined : vnDate(0),
    module: module === "all" ? undefined : module,
    action,
    page,
  };
  const { data, isPending, error, refetch } = useActivity(q);

  const byDay = new Map<string, Activity[]>();
  for (const a of data?.items ?? []) {
    const key = formatDate(a.created_at);
    byDay.set(key, [...(byDay.get(key) ?? []), a]);
  }

  return (
    <>
      <Toolbar
        end={
          <>
            {action ? (
              <Chip selected onClick={() => setAction(undefined)} aria-label={`Bỏ lọc ${actionLabel}`}>
                {actionLabel} ✕
              </Chip>
            ) : null}
            <InlineSelect
              aria-label="Khu"
              appearance="inline"
              value={module}
              onChange={(v) => {
                setModule(v);
                setPage(1);
              }}
              options={[{ value: "all", label: "Mọi khu" }, ...modules.map((m) => ({ value: m, label: moduleLabel(m) }))]}
            />
          </>
        }
      >
        {RANGES.map((r) => (
          <Chip
            key={r.value}
            selected={range === r.value}
            onClick={() => {
              setRange(r.value);
              setPage(1);
            }}
          >
            {r.label}
          </Chip>
        ))}
      </Toolbar>

      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được nhật ký"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : !data.items.length ? (
        <EmptyState icon={<History />} title="Chưa có việc nào trong khoảng này" description="Chọn khoảng ngày dài hơn hoặc bỏ bớt bộ lọc." />
      ) : (
        <>
          {[...byDay.entries()].map(([day, items]) => (
            <section key={day} className="flex flex-col gap-2" aria-label={day}>
              <h2 className="font-sans text-[13px] font-semibold text-ink-2">{formatWeekday(items[0].created_at)}</h2>
              <ul className="flex flex-col gap-2">
                {items.map((a) => (
                  <li key={a.id}>
                    <ActivityItem a={a} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <Pager page={data.page} pages={data.pages} onPage={setPage} />
        </>
      )}
    </>
  );
}

function ActivityItem({ a }: { a: Activity }) {
  const [open, setOpen] = useState(false);
  const { user } = useSession();
  const undo = useUndo();
  const confirm = useConfirm();
  const hasDetail = !!(a.rationale || a.sources.length || a.summary);

  async function doUndo() {
    const ok = await confirm({ title: "Hoàn tác việc này?", message: a.title, confirmLabel: "Hoàn tác", tone: "danger" });
    if (!ok) return;
    await undo.mutateAsync(a.id);
    notifySuccess("Đã hoàn tác");
  }

  return (
    <div className="rounded-md border border-line bg-surface p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[15px] leading-snug font-semibold [overflow-wrap:anywhere]">{a.title}</p>
          <p className="mt-0.5 text-[13px] text-ink-2">
            <DateTime value={a.created_at} format="time" /> · {a.action_label}
          </p>
        </div>
        {a.mode === "auto" ? (
          <LevelTag level="auto" size="sm">
            Tự làm
          </LevelTag>
        ) : (
          <LevelTag level="review" size="sm">
            Chị đã duyệt
          </LevelTag>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {hasDetail ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="inline-flex h-8 items-center gap-1 text-[14px] font-semibold text-accent"
          >
            Căn cứ <ChevronDown className={open ? "size-4 rotate-180 transition-transform" : "size-4 transition-transform"} aria-hidden />
          </button>
        ) : null}
        {a.href ? (
          <Link href={a.href} className="inline-flex h-8 items-center text-[14px] font-semibold text-accent">
            Mở chi tiết →
          </Link>
        ) : null}
        <span className="flex-1" />
        {a.undone_at ? (
          <Badge tone="outline">Đã hoàn tác</Badge>
        ) : a.undoable && isOwner(user) ? (
          <Button size="sm" variant="ghost" icon={<RotateCcw className="size-4" />} loading={undo.isPending} onClick={doUndo}>
            Hoàn tác
          </Button>
        ) : null}
      </div>
      {open ? (
        <div className="mt-2 flex flex-col gap-2">
          {a.summary && a.summary !== a.title ? <p className="text-[14px] text-ink-2">{a.summary}</p> : null}
          <Rationale rationale={a.rationale} sources={a.sources} />
        </div>
      ) : null}
    </div>
  );
}

const AUDIT_LABELS: Record<string, string> = {
  "control.approved": "Duyệt",
  "control.returned": "Trả lại",
  "control.approve_failed": "Duyệt nhưng lỗi",
  "control.undone": "Hoàn tác",
  "control.autonomy_changed": "Đổi mức tự chủ",
  "control.setting_changed": "Đổi cài đặt",
  "control.blocked": "AI bỏ qua (đang tắt)",
  "control.auto_failed": "AI tự làm lỗi",
  "control.command": "Ra lệnh bằng lời",
  "auth.login": "Đăng nhập",
  "auth.password_changed": "Đổi mật khẩu",
  "users.created": "Tạo tài khoản",
  "users.updated": "Sửa tài khoản",
};

const DECISIONS = ["control.approved", "control.returned", "control.approve_failed", "control.undone"];

const ACTOR_LABELS: Record<string, string> = { owner: "Chị", helper: "Người phụ", ai: "AI", system: "Hệ thống", customer: "Khách" };

function AuditLog() {
  const [scope, setScope] = useUrlParam<"decisions" | "all">("pham-vi", "decisions", ["decisions", "all"]);
  const [page, setPage] = useState(1);
  const { data, isPending, error, refetch } = useAudit({ actions: scope === "decisions" ? DECISIONS : undefined, page });
  const pick = (s: "decisions" | "all") => {
    setScope(s);
    setPage(1);
  };
  return (
    <>
      <Toolbar>
        <Chip selected={scope === "decisions"} onClick={() => pick("decisions")}>
          Duyệt, trả lại, hoàn tác
        </Chip>
        <Chip selected={scope === "all"} onClick={() => pick("all")}>
          Mọi thay đổi
        </Chip>
      </Toolbar>
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được lưu vết"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : !data.items.length ? (
        <EmptyState icon={<ShieldCheck />} title="Chưa có lưu vết" description="Mỗi lần chị duyệt, trả lại hay hoàn tác sẽ được ghi ở đây." />
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {data.items.map((e) => (
              <AuditRow key={e.id} e={e} />
            ))}
          </ul>
          <Pager page={data.page} pages={data.pages} onPage={setPage} />
        </>
      )}
    </>
  );
}

function AuditRow({ e }: { e: AuditEntry }) {
  const note = typeof e.data.note === "string" ? e.data.note : null;
  const edited = !!e.data.edited;
  return (
    <li className="flex flex-col gap-0.5 p-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 text-[15px] font-semibold">{AUDIT_LABELS[e.action] ?? e.action}</p>
        <span className="shrink-0 text-[12.5px] text-ink-3">
          <DateTime value={e.created_at} format="dateTime" />
        </span>
      </div>
      {e.summary ? <p className="text-[14px] [overflow-wrap:anywhere]">{e.summary}</p> : null}
      <p className="text-[13px] text-ink-2">
        {e.actor_name ?? ACTOR_LABELS[e.actor_kind] ?? e.actor_kind}
        {edited ? " · đã sửa trước khi duyệt" : ""}
        {note ? ` · «${note}»` : ""}
      </p>
    </li>
  );
}

function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <nav aria-label="Trang" className="flex items-center justify-between gap-3">
      <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Mới hơn
      </Button>
      <span className="text-[13px] text-ink-2">
        Trang {page}/{pages}
      </span>
      <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Cũ hơn →
      </Button>
    </nav>
  );
}
