"use client";

import { CircleAlert, CircleCheck, Plug } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, Input, PageHeader, Segmented, SkeletonList, notifySuccess, useConfirm } from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import {
  useCheckSourceAccount,
  useSaveSourceAccount,
  useSaveSourceRoute,
  useSources,
  type SourceAccount,
  type SourcePlatformCard,
  type SourceProfile,
} from "@/lib/api/control";
import { SettingsNav } from "./settings-nav";
import { SourceProfileSection } from "./source-profile-section";
import { OwnerOnly } from "./settings-screens";
import { GuideBox } from "./social-accounts-screen";

/**
 * Cài đặt → Nguồn hàng: mỗi sàn một thẻ — lấy hàng bằng Giả lập / AI tìm trên web / tài khoản dịch vụ (OneBound,
 * Rakuten API); rồi mỗi dịch vụ một thẻ — ô khoá (bí mật chỉ ghi, hiện 4 ký tự cuối), «Kiểm tra kết nối», hướng dẫn và
 * chi phí. Nội dung lấy từ backend `source_config` (xem docs/source-accounts.md). Mỗi sàn (và các nguồn không có thẻ
 * riêng) có «Cấu hình nâng cao» gập sẵn: hồ sơ đọc link và ảnh (`source_profiles`).
 */
export function SourceAccountsScreen() {
  const { user } = useSession();
  const owner = isOwner(user);
  const { data, isPending, error, refetch } = useSources(owner);
  if (user && !owner) return <OwnerOnly title="Nguồn hàng" />;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Nguồn hàng"
        description="Sàn còn «Giả lập» thì trả món mẫu, chưa lấy hàng thật."
      />
      <SettingsNav />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} action={<Button variant="secondary" onClick={() => refetch()}>Thử lại</Button>} />
      ) : (
        <>
          <section aria-label="Các sàn" className="grid gap-4 lg:grid-cols-2">
            {data.platforms.map((p) => (
              <PlatformCard key={p.platform} item={p} accounts={data.accounts} profile={data.profiles.find((x) => x.platform === p.platform)} />
            ))}
          </section>
          <OtherProfiles profiles={data.profiles.filter((x) => !data.platforms.some((p) => p.platform === x.platform))} />
          <h2 className="mt-2 text-[18px]">Tài khoản dịch vụ lấy hàng</h2>
          <p className="-mt-2 text-[14px] text-ink-2">
            Khoá dùng khi một sàn ở trên chọn «Qua …». Xu hướng, giá sàn Việt Nam và link trang lạ:{" "}
            {data.general_driver === "web" ? "AI tìm trên web" : "giả lập"}.
          </p>
          {data.accounts.map((a) => (
            <AccountCard key={a.account} item={a} platforms={data.platforms} />
          ))}
        </>
      )}
    </div>
  );
}

const STATUS: Record<SourcePlatformCard["status"], { label: string; tone: "success" | "warning" | "danger" | "neutral" }> = {
  mock: { label: "Giả lập", tone: "warning" },
  web: { label: "Dùng AI tìm trên web", tone: "neutral" },
  connected: { label: "Đã nối", tone: "success" },
  not_connected: { label: "Chưa nối", tone: "danger" },
};

function OtherProfiles({ profiles }: { profiles: SourceProfile[] }) {
  if (!profiles.length) return null;
  return (
    <section aria-label="Nguồn khác" className="flex flex-col gap-3">
      <h2 className="mt-2 text-[18px]">Nguồn khác</h2>
      <p className="-mt-2 text-[14px] text-ink-2">
        Các nguồn không có thẻ riêng luôn đi «AI tìm trên web». «Trang khác» áp cho mọi link không thuộc sàn nào ở trên.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        {profiles.map((p) => (
          <Card key={p.platform} role="region" aria-label={p.label} className="flex flex-col gap-3">
            <h3 className="text-[16px]">{p.label}</h3>
            <SourceProfileSection profile={p} />
          </Card>
        ))}
      </div>
    </section>
  );
}

function PlatformCard({ item, accounts, profile }: { item: SourcePlatformCard; accounts: SourceAccount[]; profile?: SourceProfile }) {
  const save = useSaveSourceRoute();
  const confirm = useConfirm();
  const status = STATUS[item.status];
  const account = accounts.find((a) => a.account === item.account);

  async function onChoose(driver: string) {
    if (driver === item.driver && item.driver_source === "settings") return;
    const label = item.options.find((o) => o.driver === driver)?.label ?? driver;
    if (driver !== "mock") {
      const acc = accounts.find((a) => a.driver === driver);
      const ok = await confirm({
        title: `Lấy hàng thật ở ${item.label}?`,
        message:
          driver === "web"
            ? "Mỗi lần săn hàng, AI sẽ tìm trên web và đọc trang của sàn này (tốn tiền AI theo lượt tìm). Trang cần đăng nhập thì AI không đọc được."
            : acc?.ready
              ? `Từ giờ săn hàng ở ${item.label} sẽ gọi ${acc.label} (tính tiền theo lần gọi nếu dịch vụ thu phí).`
              : `${acc?.label ?? label} chưa có khoá: săn hàng ở ${item.label} sẽ báo lỗi cho tới khi chị nhập khoá ở thẻ bên dưới.`,
        confirmLabel: "Chạy thật",
      });
      if (!ok) return;
    }
    await save.mutateAsync({ platform: item.platform, driver });
    notifySuccess(`${item.label}: ${label}`);
  }

  return (
    <Card role="region" aria-label={item.label} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-2 text-[18px]">
            {item.label}
            <Badge tone={status.tone}>{status.label}</Badge>
          </h2>
          {item.driver_source === "env" ? <p className="mt-0.5 text-[13px] text-ink-2">Đang theo cài đặt máy chủ.</p> : null}
        </div>
        <Segmented<string>
          aria-label={`Cách lấy hàng ở ${item.label}`}
          value={item.driver}
          onChange={onChoose}
          size="sm"
          className="max-w-full overflow-x-auto"
          options={item.options.map((o) => ({ value: o.driver, label: o.label }))}
        />
      </div>
      {account ? (
        <p className="flex items-center gap-1.5 text-[14px] text-ink-2">
          {account.ready ? <CircleCheck className="size-4 text-auto" aria-hidden /> : <CircleAlert className="size-4 text-seal" aria-hidden />}
          <a href={`#tk-${account.account}`} className="text-accent hover:underline">
            {account.label}
          </a>
          : {account.ready ? "đã có khoá" : "chưa có khoá"}.
        </p>
      ) : null}
      {item.warning ? <p className="text-[13px] text-seal">{item.warning}</p> : null}
      <ul className="list-disc pl-5 text-[13px] text-ink-2">
        {item.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      {profile ? <SourceProfileSection profile={profile} /> : null}
    </Card>
  );
}

function AccountCard({ item, platforms }: { item: SourceAccount; platforms: SourcePlatformCard[] }) {
  const save = useSaveSourceAccount();
  const check = useCheckSourceAccount();
  const saved = (f: SourceAccount["fields"][number]) => (f.secret ? "" : f.source === "settings" ? (f.value ?? "") : "");
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(item.fields.map((f) => [f.key, saved(f)])));
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const dirty = item.fields.some((f) => (values[f.key] ?? "") !== saved(f));
  const label = (code: string) => platforms.find((p) => p.platform === code)?.label ?? code;

  async function onSave() {
    const out: Record<string, string> = {};
    for (const f of item.fields) {
      const v = (values[f.key] ?? "").trim();
      if (f.secret ? v : v !== saved(f)) out[f.key] = v;
    }
    const clear = item.fields.filter((f) => !f.secret && f.source === "settings" && !(values[f.key] ?? "").trim()).map((f) => f.key);
    if (!Object.keys(out).length && !clear.length) return notifySuccess("Không có gì thay đổi");
    await save.mutateAsync({ account: item.account, values: out, clear });
    setValues((v) => Object.fromEntries(Object.entries(v).map(([k, x]) => [k, item.fields.find((f) => f.key === k)?.secret ? "" : x])));
    setResult(null);
    notifySuccess(`Đã lưu ${item.label}`);
  }

  async function onCheck() {
    const typed = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim()));
    setResult(await check.mutateAsync({ account: item.account, values: typed }));
  }

  const shown = result ?? item.check;

  return (
    <Card id={`tk-${item.account}`} role="region" aria-label={item.label} className="flex scroll-mt-20 flex-col gap-4">
      <div className="min-w-0">
        <h2 className="flex flex-wrap items-center gap-2 text-[18px]">
          {item.label}
          <Badge tone={item.ready ? "success" : "danger"}>{item.ready ? "Đã có khoá" : "Chưa có khoá"}</Badge>
          {!item.verified ? <Badge tone="outline">Chưa thử với khoá thật</Badge> : null}
        </h2>
        <p className="mt-0.5 text-[13px] text-ink-2">
          Lấy được: {item.platforms.map(label).join(", ")}
          {" · "}
          {item.used_by.length ? `đang dùng cho ${item.used_by.map(label).join(", ")}` : "chưa sàn nào chọn"}
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-3">
          {item.fields.map((f) => (
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
          <div className="flex flex-wrap gap-2">
            <Button onClick={onSave} loading={save.isPending} disabled={!dirty}>
              Lưu
            </Button>
            <Button variant="secondary" icon={<Plug className="size-4" />} onClick={onCheck} loading={check.isPending}>
              Kiểm tra kết nối
            </Button>
          </div>
          {shown ? (
            <p aria-label="Kết quả kiểm tra" className={shown.ok ? "text-[14px] text-auto" : "text-[14px] text-seal"}>
              {shown.ok ? "✓ " : "✗ "}
              {shown.message}
            </p>
          ) : null}
        </div>
        <GuideBox title={`Hướng dẫn lấy khoá ${item.label}`} guide={item.guide} open={!item.ready} />
      </div>
    </Card>
  );
}
