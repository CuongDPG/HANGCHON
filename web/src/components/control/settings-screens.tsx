"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight, Plug, RotateCw, Share2, UserPlus, UsersRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Badge,
  Button,
  Card,
  CardLink,
  DataList,
  EmptyState,
  Input,
  PageHeader,
  SectionLabel,
  Segmented,
  Sheet,
  SkeletonList,
  Textarea,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { authApi, isOwner, useSession, type SessionUser } from "@/lib/api/auth";
import {
  useCreateUser,
  useIntegrations,
  useSaveSettings,
  useSettings,
  useUpdateUser,
  useUsers,
  type Integration,
} from "@/lib/api/control";
import { formatNumber } from "@/lib/format";
import type { ThemePreference } from "@/lib/theme";
import { useThemePreference } from "@/lib/use-theme";
import { useMutation } from "@tanstack/react-query";
import { SettingsNav } from "./settings-nav";

/* ---------- khung chung ---------- */

export function OwnerOnly({ title }: { title: string }) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={title} />
      <SettingsNav />
      <EmptyState title="Chỉ chị (chủ cửa hàng) xem được phần này" />
    </div>
  );
}

/* ---------- cửa hàng ---------- */

// Tên ô trong form KHÔNG có dấu chấm: react-hook-form hiểu «store.name» là đường dẫn lồng nhau
// (ghi vào values.store.name) còn zod lọc mất → bấm Lưu gửi lại giá trị cũ. Lưu thì ghép «store.» vào.
const STORE_FIELDS = [
  "name",
  "tagline",
  "picker_name",
  "picker_intro",
  "bank_code",
  "bank_account_no",
  "bank_account_name",
  "default_shipping_fee_vnd",
] as const;

const storeSchema = z.object({
  name: z.string().trim().min(1, "Cửa hàng cần có tên").max(80),
  tagline: z.string().max(160, "Tối đa 160 ký tự"),
  picker_name: z.string().max(80, "Tối đa 80 ký tự"),
  picker_intro: z.string().max(1500, "Tối đa 1.500 ký tự"),
  bank_code: z.string().max(20, "Tối đa 20 ký tự"),
  bank_account_no: z.string().regex(/^\d{0,20}$/, "Số tài khoản chỉ gồm chữ số"),
  bank_account_name: z.string().max(80, "Tối đa 80 ký tự"),
  default_shipping_fee_vnd: z.string().regex(/^[\d.]*$/, "Nhập số tiền"),
});
type StoreValues = z.infer<typeof storeSchema>;

export function StoreSettingsScreen() {
  const { data, isPending, error, refetch } = useSettings();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Cửa hàng" description="Hiện trên website và trong tin nhắn gửi khách." />
      <SettingsNav />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được cài đặt"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : (
        <StoreForm values={Object.fromEntries(data.map((s) => [s.key, s.value]))} />
      )}
    </div>
  );
}

function StoreForm({ values }: { values: Record<string, unknown> }) {
  const { user } = useSession();
  const owner = isOwner(user);
  const save = useSaveSettings();
  const defaults = Object.fromEntries(
    STORE_FIELDS.map((f) => {
      const v = values[`store.${f}`];
      return [f, f === "default_shipping_fee_vnd" ? formatNumber(Number(v ?? 0)) : String(v ?? "")];
    }),
  ) as StoreValues;
  const { register, handleSubmit, formState, reset } = useForm<StoreValues>({ resolver: zodResolver(storeSchema), defaultValues: defaults });
  const e = formState.errors;

  const onSubmit = handleSubmit(async (v) => {
    const out: Record<string, unknown> = {};
    for (const f of STORE_FIELDS) {
      const next = f === "default_shipping_fee_vnd" ? Number(v[f].replace(/\D/g, "") || 0) : v[f].trim();
      if (next !== (values[`store.${f}`] ?? "")) out[`store.${f}`] = next;
    }
    if (!Object.keys(out).length) return notifySuccess("Không có gì thay đổi");
    await save.mutateAsync(out);
    reset(v);
    notifySuccess("Đã lưu thông tin cửa hàng");
  });

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Cửa hàng</SectionLabel>
        <Input label="Tên cửa hàng" error={e.name?.message} {...register("name")} />
        <Input label="Câu giới thiệu" hint="Một dòng dưới tên cửa hàng." error={e.tagline?.message} {...register("tagline")} />
      </fieldset>
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Người chọn</SectionLabel>
        <Input label="Tên người chọn" placeholder="Vd: Mai" hint="Khách thấy tên này ở trang «Về người chọn» và trong khung hỏi đáp; chỉ ghi tên, không thêm «chị»." error={e.picker_name?.message} {...register("picker_name")} />
        <Textarea label="Lời giới thiệu" rows={4} placeholder="Vd: Mình chọn hàng thế nào, thử bao lâu, vì sao bán…" hint="Khách đọc đoạn này ở trang «Về người chọn»: viết xưng «mình»." error={e.picker_intro?.message} {...register("picker_intro")} />
      </fieldset>
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Nhận chuyển khoản</SectionLabel>
        <div className="grid grid-cols-[7rem_1fr] gap-3">
          <Input label="Ngân hàng" placeholder="VCB" error={e.bank_code?.message} {...register("bank_code")} />
          <Input label="Số tài khoản" inputMode="numeric" error={e.bank_account_no?.message} {...register("bank_account_no")} />
        </div>
        <Input label="Tên chủ tài khoản" hint="Viết hoa không dấu, đúng như trên ngân hàng." error={e.bank_account_name?.message} {...register("bank_account_name")} />
      </fieldset>
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Giao hàng</SectionLabel>
        <Input
          label="Phí giao mặc định"
          inputMode="numeric"
          trailing="đ"
          hint="Áp khi chưa lấy được báo giá của hãng giao."
          error={e.default_shipping_fee_vnd?.message}
          {...register("default_shipping_fee_vnd")}
        />
      </fieldset>
      {owner ? (
        <Button type="submit" loading={save.isPending} disabled={!formState.isDirty} className="self-start">
          Lưu thay đổi
        </Button>
      ) : (
        <p className="text-[14px] text-ink-2">Chỉ chị (chủ cửa hàng) sửa được phần này.</p>
      )}
    </form>
  );
}

/* ---------- tài khoản: đổi mật khẩu ---------- */

const pwSchema = z
  .object({
    current_password: z.string().min(1, "Nhập mật khẩu hiện tại"),
    new_password: z.string().min(8, "Mật khẩu mới ít nhất 8 ký tự").max(200),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Hai lần nhập chưa khớp" });
type PwValues = z.infer<typeof pwSchema>;

export function AccountScreen() {
  const { user } = useSession();
  const change = useMutation({ mutationFn: authApi.changePassword, meta: { silentError: true } });
  const { register, handleSubmit, formState, reset, setError } = useForm<PwValues>({ resolver: zodResolver(pwSchema) });
  const onSubmit = handleSubmit(async (v) => {
    try {
      await change.mutateAsync({ current_password: v.current_password, new_password: v.new_password });
    } catch (err) {
      setError("current_password", { message: err instanceof Error ? err.message : "Chưa đổi được" });
      return;
    }
    reset();
    notifySuccess("Đã đổi mật khẩu");
  });
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Tài khoản của chị" />
      <SettingsNav />
      {user ? (
        <Card flush className="px-4 py-2">
          <DataList
            items={[
              { label: "Tên", value: user.name },
              { label: "Email", value: <span className="break-all">{user.email}</span> },
              { label: "Vai trò", value: isOwner(user) ? "Chủ cửa hàng" : "Người phụ giúp" },
            ]}
          />
        </Card>
      ) : null}
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <SectionLabel>Đổi mật khẩu</SectionLabel>
        <Input label="Mật khẩu hiện tại" type="password" autoComplete="current-password" error={formState.errors.current_password?.message} {...register("current_password")} />
        <Input label="Mật khẩu mới" type="password" autoComplete="new-password" error={formState.errors.new_password?.message} {...register("new_password")} />
        <Input label="Nhập lại mật khẩu mới" type="password" autoComplete="new-password" error={formState.errors.confirm?.message} {...register("confirm")} />
        <Button type="submit" loading={change.isPending} className="self-start">
          Đổi mật khẩu
        </Button>
      </form>
      <ThemeSection />
    </div>
  );
}

/** Giao diện sáng/tối (lưu trên máy này). Xem trước cả hai ở «Bộ giao diện». */
function ThemeSection() {
  const [theme, setTheme] = useThemePreference();
  return (
    <section className="flex flex-col gap-3" aria-label="Giao diện">
      <SectionLabel>Giao diện</SectionLabel>
      <Segmented<ThemePreference>
        aria-label="Giao diện"
        value={theme}
        onChange={setTheme}
        options={[
          { value: "system", label: "Theo máy" },
          { value: "light", label: "Sáng" },
          { value: "dark", label: "Tối" },
        ]}
        className="self-start"
      />
      <p className="text-[13px] text-ink-2">Chỉ đổi trên máy này. «Theo máy» tự sáng/tối theo cài đặt của điện thoại hoặc máy tính.</p>
    </section>
  );
}

/* ---------- người phụ giúp (k4) ---------- */

export function HelpersScreen() {
  const { user } = useSession();
  const owner = isOwner(user);
  const users = useUsers(owner);
  const update = useUpdateUser();
  const confirm = useConfirm();
  const [creating, setCreating] = useState(false);
  const [resetFor, setResetFor] = useState<SessionUser | null>(null);
  if (user && !owner) return <OwnerOnly title="Người phụ giúp" />;
  const helpers = (users.data ?? []).filter((u) => u.role === "helper");

  async function toggle(u: SessionUser) {
    if (u.is_active) {
      const ok = await confirm({ title: `Khoá tài khoản ${u.name}?`, message: "Người này sẽ bị đăng xuất và không vào được bàn làm việc.", confirmLabel: "Khoá", tone: "danger" });
      if (!ok) return;
    }
    await update.mutateAsync({ id: u.id, is_active: !u.is_active });
    notifySuccess(u.is_active ? `Đã khoá ${u.name}` : `Đã mở lại ${u.name}`);
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Người phụ giúp"
        description="Người phụ xem được mọi thứ, ghi chi phí; không duyệt, không đổi cài đặt."
        actions={
          <Button size="sm" icon={<UserPlus className="size-4" />} onClick={() => setCreating(true)}>
            Thêm người phụ giúp
          </Button>
        }
      />
      <SettingsNav />
      {users.isPending ? (
        <SkeletonList rows={2} />
      ) : users.error ? (
        <EmptyState tone="error" title="Chưa tải được danh sách" description={users.error.message} />
      ) : !helpers.length ? (
        <EmptyState icon={<UsersRound />} title="Chưa có người phụ giúp" description="Tạo tài khoản cho người giúp chị đóng gói, trả lời khách, ghi chi phí." />
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {helpers.map((u) => (
            <li key={u.id} className="flex flex-col gap-2 p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[15px] font-semibold">{u.name}</p>
                  <p className="text-[13px] break-all text-ink-2">{u.email}</p>
                </div>
                <Badge tone={u.is_active ? "success" : "outline"}>{u.is_active ? "Đang dùng" : "Đã khoá"}</Badge>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setResetFor(u)}>
                  Đặt lại mật khẩu
                </Button>
                <Button size="sm" variant={u.is_active ? "ghost" : "secondary"} onClick={() => toggle(u)}>
                  {u.is_active ? "Khoá" : "Mở khoá"}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <CreateHelperSheet open={creating} onClose={() => setCreating(false)} />
      <ResetPasswordSheet user={resetFor} onClose={() => setResetFor(null)} />
    </div>
  );
}

const helperSchema = z.object({
  name: z.string().trim().min(1, "Nhập tên").max(120),
  email: z.string().trim().regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/, "Email chưa đúng"),
  password: z.string().min(8, "Ít nhất 8 ký tự"),
});
type HelperValues = z.infer<typeof helperSchema>;

function CreateHelperSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateUser();
  const { register, handleSubmit, formState, reset } = useForm<HelperValues>({ resolver: zodResolver(helperSchema) });
  const close = () => {
    reset();
    onClose();
  };
  const onSubmit = handleSubmit(async (v) => {
    await create.mutateAsync(v);
    notifySuccess(`Đã tạo tài khoản cho ${v.name}`);
    close();
  });
  return (
    <Sheet
      open={open}
      onClose={close}
      title="Thêm người phụ giúp"
      description="Gửi email và mật khẩu này cho người phụ; họ đổi mật khẩu sau khi đăng nhập."
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Huỷ
          </Button>
          <Button type="submit" form="helper-form" loading={create.isPending}>
            Tạo tài khoản
          </Button>
        </>
      }
    >
      <form id="helper-form" onSubmit={onSubmit} className="flex flex-col gap-3">
        <Input label="Tên" error={formState.errors.name?.message} {...register("name")} />
        <Input label="Email" type="email" autoComplete="off" error={formState.errors.email?.message} {...register("email")} />
        <Input label="Mật khẩu ban đầu" type="text" autoComplete="new-password" error={formState.errors.password?.message} {...register("password")} />
      </form>
    </Sheet>
  );
}

function ResetPasswordSheet({ user, onClose }: { user: SessionUser | null; onClose: () => void }) {
  const update = useUpdateUser();
  const [pw, setPw] = useState("");
  const close = () => {
    setPw("");
    onClose();
  };
  return (
    <Sheet
      open={!!user}
      onClose={close}
      title="Đặt lại mật khẩu"
      description={user ? `Cho ${user.name}` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Huỷ
          </Button>
          <Button
            loading={update.isPending}
            disabled={pw.length < 8}
            onClick={async () => {
              if (!user) return;
              await update.mutateAsync({ id: user.id, password: pw });
              notifySuccess("Đã đặt mật khẩu mới");
              close();
            }}
          >
            Lưu mật khẩu
          </Button>
        </>
      }
    >
      <Input label="Mật khẩu mới" type="text" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} hint="Ít nhất 8 ký tự." />
    </Sheet>
  );
}

/* ---------- tích hợp ---------- */

/** Tên dịch vụ dễ hiểu thay cho tên driver trong cấu hình. */
const DRIVER_LABELS: Record<string, string> = {
  sepay: "SePay (chuyển khoản tự khớp)",
  ghn: "Giao Hàng Nhanh",
  ghtk: "Giao Hàng Tiết Kiệm",
  onebound: "OneBound (1688, Taobao)",
  rakuten: "Rakuten API",
  web: "AI tìm trên web",
  local: "Lưu trên máy chủ",
  s3: "Kho lưu trữ đám mây",
  meta: "Facebook, Instagram",
  threads: "Threads",
  zalo_oa: "Zalo OA",
  tiktok_draft: "TikTok",
  smtp: "Email",
  anthropic: "Claude",
};

function integrationLine(i: Integration): string {
  const real = i.drivers.filter((d) => d !== "mock").map((d) => DRIVER_LABELS[d] ?? d);
  if (i.is_mock) return "Đang chạy thử, chưa nối tài khoản thật";
  if (i.partly_mock) return `Đã nối: ${real.join(", ")} · kênh khác còn giả lập`;
  return `Đang nối: ${real.join(", ") || (DRIVER_LABELS[i.driver] ?? i.driver)}`;
}

function integrationTone(i: Integration): "danger" | "warning" | "success" {
  if (i.blocked_in_prod) return "danger";
  return i.is_mock || i.partly_mock ? "warning" : "success";
}

/** Thẻ tóm tắt: bao nhiêu tích hợp chạy thật, bao nhiêu còn giả lập (khách không nhận được gì từ phần giả lập). */
export function IntegrationSummary({ items, href }: { items: Integration[]; href?: string }) {
  const mock = items.filter((i) => i.is_mock || i.partly_mock);
  const real = items.length - mock.length;
  const blocked = items.some((i) => i.blocked_in_prod);
  const body = (
    <>
      <span className="flex items-center gap-2">
        <Plug className={mock.length ? "size-5 shrink-0 text-review" : "size-5 shrink-0 text-auto"} aria-hidden />
        <span className="text-[15px] font-semibold">
          {mock.length ? `${real} tích hợp chạy thật · ${mock.length} còn giả lập` : "Mọi tích hợp đều chạy thật"}
        </span>
        {href ? <ChevronRight className="ml-auto size-4 shrink-0 text-ink-3" aria-hidden /> : null}
      </span>
      {mock.length ? (
        <span className="mt-1 block text-[13px] text-ink-2">
          Còn giả lập: {mock.map((i) => i.label).join(", ")}. Phần giả lập không gửi gì tới khách hay đối tác thật.
          {blocked ? " Hoá đơn điện tử bị chặn phát hành ở bản chạy thật." : ""}
        </span>
      ) : null}
    </>
  );
  const tone = blocked ? "danger" : mock.length ? "accent" : "default";
  return href ? (
    <CardLink href={href} tone={tone} aria-label="Xem trạng thái tích hợp">
      {body}
    </CardLink>
  ) : (
    <Card tone={tone}>{body}</Card>
  );
}

export function IntegrationsScreen() {
  const { data, isPending, error } = useIntegrations();
  const { user } = useSession();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Tích hợp" description="«Giả lập» nghĩa là chưa nối tài khoản thật, không gửi gì ra ngoài." />
      <SettingsNav />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : (
        <>
          <IntegrationSummary items={data} />
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
            {data.map((i) => (
              <li key={i.kind} className="flex items-start justify-between gap-3 p-3.5">
                <div className="min-w-0">
                  <p className="text-[15px] font-semibold">{i.label}</p>
                  <p className="text-[13px] text-ink-2">{integrationLine(i)}</p>
                  {i.mock_effect ? <p className="text-[13px] text-ink-2">{i.mock_effect}</p> : null}
                  {i.blocked_in_prod ? <p className="text-[13px] font-medium text-seal">Bản chạy thật đang chặn phát hành cho tới khi nối nhà cung cấp.</p> : null}
                </div>
                <Badge tone={integrationTone(i)}>{i.is_mock ? "Giả lập" : i.partly_mock ? "Một phần" : "Thật"}</Badge>
              </li>
            ))}
          </ul>
        </>
      )}
      {isOwner(user) ? (
        <Link
          href="/desk/cai-dat/mang-xa-hoi"
          className="flex items-center gap-3 rounded-md border border-line bg-surface p-3.5 transition-colors hover:bg-soft-2"
        >
          <Share2 className="size-5 shrink-0 text-accent" aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold">Mạng xã hội và sàn</span>
            <span className="block text-[13px] text-ink-2">Chị tự nối Facebook, Instagram, Threads, TikTok, Zalo OA, Shopee, TikTok Shop và bật chạy thật từng kênh.</span>
          </span>
          <ChevronRight className="size-4 shrink-0 text-ink-3" aria-hidden />
        </Link>
      ) : null}
      <p className="text-[13px] text-ink-2">
        Thanh toán, vận chuyển, báo tin, hoá đơn điện tử: chị gửi thông tin tài khoản cho người cài máy chủ; họ bật theo tài liệu triển khai.
      </p>
    </div>
  );
}
