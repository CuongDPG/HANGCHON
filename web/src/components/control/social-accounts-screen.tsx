"use client";

import { CircleCheck, CircleAlert, ExternalLink, Link2, Plug } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  DateTime,
  EmptyState,
  Input,
  PageHeader,
  Segmented,
  SkeletonList,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import {
  useChannelAccounts,
  useCheckChannelAccount,
  useConnectChannelAccount,
  useSaveChannelAccount,
  type ChannelAccount,
} from "@/lib/api/control";
import { SettingsNav } from "./settings-nav";
import { OwnerOnly } from "./settings-screens";

/**
 * Cài đặt → Mạng xã hội: mỗi kênh một thẻ — trạng thái, công tắc Giả lập / Chạy thật, ô khoá cần cho driver thật
 * (bí mật chỉ ghi, hiện 4 ký tự cuối), «Kiểm tra kết nối», nút «Kết nối» với kênh phải cấp quyền qua trang của nền tảng,
 * và hướng dẫn từng bước (chép từ docs/channel-accounts.md, nguồn là backend `channel_config.SPECS`).
 */
export function SocialAccountsScreen() {
  const { user } = useSession();
  const owner = isOwner(user);
  const { data, isPending, error, refetch } = useChannelAccounts(owner);
  useOAuthResult(data);
  if (user && !owner) return <OwnerOnly title="Mạng xã hội" />;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Mạng xã hội"
        description="Kênh còn «Giả lập» thì không gửi gì ra ngoài."
      />
      <SettingsNav />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} action={<Button variant="secondary" onClick={() => refetch()}>Thử lại</Button>} />
      ) : (
        <>
          <Overview items={data} />
          {data.map((c) => (
            <ChannelCard key={c.channel} item={c} />
          ))}
        </>
      )}
    </div>
  );
}

/** Sau khi nền tảng chuyển chị về (?kenh=…&ket_qua=ok|loi&loi=…): báo một lần rồi bỏ tham số khỏi URL. */
function useOAuthResult(data: ChannelAccount[] | undefined) {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const done = useRef(false);
  useEffect(() => {
    const result = params.get("ket_qua");
    if (!result || done.current || !data) return;
    done.current = true;
    const label = data.find((c) => c.channel === params.get("kenh"))?.label ?? "kênh";
    if (result === "ok") notifySuccess(`Đã kết nối ${label}`);
    else notifyError(`Chưa kết nối được ${label}: ${params.get("loi") ?? "lỗi không rõ"}`);
    router.replace(path);
  }, [params, data, router, path]);
}

const STATUS: Record<ChannelAccount["status"], { label: string; tone: "neutral" | "success" | "warning" | "danger" | "outline" }> = {
  connected: { label: "Đã nối thật", tone: "success" },
  not_connected: { label: "Chưa nối", tone: "danger" },
  mock: { label: "Giả lập", tone: "warning" },
  manual: { label: "Làm tay", tone: "outline" },
};

function Overview({ items }: { items: ChannelAccount[] }) {
  return (
    <Card flush className="overflow-x-auto">
      <ul className="flex min-w-max divide-x divide-line">
        {items.map((c) => (
          <li key={c.channel}>
            <a href={`#kenh-${c.channel}`} className="flex flex-col gap-1 px-4 py-3 hover:bg-soft-2">
              <span className="text-[14px] font-semibold">{c.label}</span>
              <Badge tone={STATUS[c.status].tone} className="self-start">{STATUS[c.status].label}</Badge>
            </a>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ChannelCard({ item }: { item: ChannelAccount }) {
  const save = useSaveChannelAccount();
  const check = useCheckChannelAccount();
  const connect = useConnectChannelAccount();
  const confirm = useConfirm();
  const editable = item.fields.filter((f) => !f.oauth);
  const oauthFields = item.fields.filter((f) => f.oauth);
  const blank = () => Object.fromEntries(editable.map((f) => [f.key, f.secret ? "" : (f.source === "settings" ? f.value ?? "" : "")]));
  const [values, setValues] = useState<Record<string, string>>(blank);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const dirty = editable.some((f) => (values[f.key] ?? "") !== (f.secret ? "" : f.source === "settings" ? f.value ?? "" : ""));
  const status = STATUS[item.status];

  async function onMode(mode: "mock" | "real") {
    if (mode === item.mode && item.mode_source === "settings") return;
    if (mode === "real") {
      const ok = await confirm({
        title: `Chạy thật ${item.label}?`,
        message: item.ready
          ? "Từ giờ việc đã được chị duyệt sẽ gửi thật lên kênh này (đăng bài, trả lời khách, đồng bộ đơn)."
          : "Kênh chưa đủ khoá: bật chạy thật thì việc gửi lên kênh này sẽ báo lỗi cho tới khi chị nối xong.",
        confirmLabel: "Chạy thật",
      });
      if (!ok) return;
    }
    await save.mutateAsync({ channel: item.channel, mode });
    notifySuccess(mode === "real" ? `${item.label}: đã bật chạy thật` : `${item.label}: chuyển về giả lập`);
  }

  async function onSave() {
    const out: Record<string, string> = {};
    for (const f of editable) {
      const v = (values[f.key] ?? "").trim();
      if (f.secret ? v : v !== (f.source === "settings" ? f.value ?? "" : "")) out[f.key] = v;
    }
    const clear = editable.filter((f) => !f.secret && f.source === "settings" && !(values[f.key] ?? "").trim()).map((f) => f.key);
    if (!Object.keys(out).length && !clear.length) return notifySuccess("Không có gì thay đổi");
    await save.mutateAsync({ channel: item.channel, values: out, clear });
    setValues((v) => Object.fromEntries(Object.entries(v).map(([k, x]) => [k, editable.find((f) => f.key === k)?.secret ? "" : x])));
    setResult(null);
    notifySuccess(`Đã lưu ${item.label}`);
  }

  async function onCheck() {
    const typed = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
    const r = await check.mutateAsync({ channel: item.channel, values: typed });
    setResult(r);
  }

  async function onConnect() {
    const r = await connect.mutateAsync(item.channel);
    window.location.assign(r.url);
  }

  const shown = result ?? item.check;

  return (
    <Card id={`kenh-${item.channel}`} role="region" aria-label={item.label} className="flex scroll-mt-20 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-2 text-[18px]">
            {item.label}
            <Badge tone={status.tone}>{status.label}</Badge>
          </h2>
          <p className="mt-0.5 text-[13px] text-ink-2">
            {item.account_name ? `Tài khoản: ${item.account_name}` : item.status === "manual" ? "Không có API: chị đăng tay." : "Chưa biết tên tài khoản — bấm «Kiểm tra kết nối»."}
            {item.mode_source === "env" && item.kind !== "manual" ? " · Công tắc đang theo cài đặt máy chủ." : ""}
          </p>
        </div>
        {item.kind !== "manual" ? (
          <Segmented<"mock" | "real">
            aria-label={`Chế độ ${item.label}`}
            value={item.mode}
            onChange={onMode}
            options={[
              { value: "mock", label: "Giả lập" },
              { value: "real", label: "Chạy thật" },
            ]}
          />
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-3">
          {editable.map((f) => (
            <Input
              key={f.key}
              label={f.required ? f.label : `${f.label} (không bắt buộc)`}
              type={f.secret ? "password" : "text"}
              autoComplete="off"
              spellCheck={false}
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              placeholder={
                f.secret
                  ? f.is_set
                    ? `Đã lưu ${f.masked ?? ""}${f.source === "env" ? " (máy chủ)" : ""} — để trống nếu giữ`
                    : "Chưa có"
                  : f.source === "env"
                    ? `${f.value} (máy chủ)`
                    : ""
              }
              hint={f.hint || undefined}
            />
          ))}
          {item.shared.map((s) => (
            <p key={`${s.channel}.${s.key}`} className="flex items-center gap-1.5 text-[14px] text-ink-2">
              {s.is_set ? <CircleCheck className="size-4 text-auto" aria-hidden /> : <CircleAlert className="size-4 text-seal" aria-hidden />}
              {s.label}: dùng chung của thẻ «Trang Facebook» — {s.is_set ? "đã có" : "chưa có"}.
            </p>
          ))}
          {item.oauth.supported ? <OAuthBlock item={item} fields={oauthFields} onConnect={onConnect} connecting={connect.isPending} /> : null}
          {item.kind !== "manual" ? (
            <div className="flex flex-wrap gap-2">
              <Button onClick={onSave} loading={save.isPending} disabled={!dirty}>
                Lưu
              </Button>
              <Button variant="secondary" icon={<Plug className="size-4" />} onClick={onCheck} loading={check.isPending}>
                Kiểm tra kết nối
              </Button>
            </div>
          ) : null}
          {shown ? (
            <p aria-label="Kết quả kiểm tra" className={shown.ok ? "text-[14px] text-auto" : "text-[14px] text-seal"}>
              {shown.ok ? "✓ " : "✗ "}
              {shown.message}
            </p>
          ) : null}
        </div>
        <Guide item={item} />
      </div>
    </Card>
  );
}

function OAuthBlock({
  item,
  fields,
  onConnect,
  connecting,
}: {
  item: ChannelAccount;
  fields: ChannelAccount["fields"];
  onConnect: () => void;
  connecting: boolean;
}) {
  const appReady = item.fields.filter((f) => !f.oauth && f.required).every((f) => f.is_set);
  return (
    <div className="flex flex-col gap-2 rounded-md border border-line bg-soft/50 p-3">
      <p className="text-[13px] text-ink-2">
        Redirect URI (dán vào ứng dụng trên trang nhà phát triển):
        <code className="mt-1 block rounded-sm bg-surface px-2 py-1 text-[13px] break-all text-ink">{item.oauth.redirect_uri}</code>
      </p>
      <p className="text-[14px]">
        {item.oauth.connected ? (
          <>
            Đã kết nối
            {item.oauth.expires_at ? (
              <span className="text-ink-2">
                {" "}
                · token hết hạn <DateTime value={new Date(item.oauth.expires_at * 1000).toISOString()} format="dateTime" />, tự làm mới
              </span>
            ) : null}
          </>
        ) : (
          <span className="text-ink-2">Chưa kết nối.</span>
        )}
      </p>
      {fields.some((f) => f.is_set) ? (
        <ul className="text-[13px] text-ink-2">
          {fields
            .filter((f) => f.is_set)
            .map((f) => (
              <li key={f.key}>
                {f.label}: {f.secret ? f.masked : f.value}
              </li>
            ))}
        </ul>
      ) : null}
      <Button
        variant={item.oauth.connected ? "secondary" : "primary"}
        icon={<Link2 className="size-4" />}
        onClick={onConnect}
        loading={connecting}
        disabled={!appReady}
        className="self-start"
      >
        {item.oauth.connected ? `Kết nối lại ${item.label}` : `Kết nối ${item.label}`}
      </Button>
      {!appReady ? <p className="text-[13px] text-ink-2">Lưu khoá ứng dụng ở trên trước rồi mới kết nối.</p> : null}
    </div>
  );
}

function Guide({ item }: { item: ChannelAccount }) {
  return <GuideBox title={`Hướng dẫn nối ${item.label}`} guide={item.guide} open={!item.ready} />;
}

export type GuideData = ChannelAccount["guide"] & { cost?: string[] };

/** Hộp «Chị cần chuẩn bị… Bước 1, 2, 3…» dùng chung cho Mạng xã hội và Nguồn hàng. */
export function GuideBox({ title, guide: g, open }: { title: string; guide: GuideData; open: boolean }) {
  return (
    <details open={open} className="rounded-md bg-soft/60 p-3 text-[14px] [&[open]>summary]:mb-2">
      <summary className="cursor-pointer font-semibold">{title}</summary>
      {g.needs.length ? (
        <>
          <p className="font-semibold">Chị cần chuẩn bị:</p>
          <ul className="mb-2 list-disc pl-5 text-ink-2">
            {g.needs.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
      <ol className="mb-2 flex flex-col gap-1 text-ink-2">
        {g.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      {g.limits.length ? (
        <>
          <p className="font-semibold">Lưu ý:</p>
          <ul className="mb-2 list-disc pl-5 text-ink-2">
            {g.limits.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
      {g.cost?.length ? (
        <>
          <p className="font-semibold">Chi phí ước tính:</p>
          <ul className="mb-2 list-disc pl-5 text-ink-2">
            {g.cost.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      ) : null}
      {g.links.length ? (
        <ul className="flex flex-col gap-1">
          {g.links.map((l) => (
            <li key={l.url}>
              <a href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
                {l.label}
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}
