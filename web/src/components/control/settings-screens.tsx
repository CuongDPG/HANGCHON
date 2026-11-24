"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronRight, DatabaseBackup, KeyRound, Plug, RotateCw, Store, UserPlus, UsersRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Badge,
  Button,
  Card,
  DataList,
  EmptyState,
  Input,
  PageHeader,
  SectionLabel,
  Sheet,
  SkeletonList,
  Textarea,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { authApi, isOwner, useSession, type SessionUser } from "@/lib/api/auth";
import { useCreateUser, useIntegrations, useSaveSettings, useSettings, useUpdateUser, useUsers } from "@/lib/api/control";
import { formatNumber } from "@/lib/format";
import { useMutation } from "@tanstack/react-query";

/* ---------- mục lục ---------- */

const SECTIONS = [
  { href: "/desk/cai-dat/cua-hang", icon: Store, title: "Cửa hàng", description: "Tên, người chọn, lời giới thiệu, tài khoản nhận tiền, phí giao" },
  { href: "/desk/cai-dat/tai-khoan", icon: KeyRound, title: "Tài khoản của chị", description: "Đổi mật khẩu đăng nhập" },
  { href: "/desk/cai-dat/nguoi-phu-giup", icon: UsersRound, title: "Người phụ giúp", description: "Tạo, khoá, đặt lại mật khẩu tài khoản phụ", owner: true },
  { href: "/desk/cai-dat/sao-luu", icon: DatabaseBackup, title: "Sao lưu", description: "Sao lưu dữ liệu hằng ngày, tải bản sao về máy", owner: true },
  { href: "/desk/cai-dat/tich-hop", icon: Plug, title: "Tích hợp", description: "Mạng xã hội, thanh toán, vận chuyển… đang chạy giả lập hay thật" },
];

export function SettingsIndex() {
  const { user } = useSession();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Cài đặt" description="Cửa hàng, tài khoản, người phụ giúp, sao lưu, tích hợp." />
      <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
        {SECTIONS.filter((s) => !s.owner || isOwner(user)).map((s) => (
          <li key={s.href}>
            <Link href={s.href} className="flex items-center gap-3 p-3.5 transition-colors hover:bg-soft-2">
              <s.icon className="size-5 shrink-0 text-accent" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold">{s.title}</span>
                <span className="block text-[13px] text-ink-2">{s.description}</span>
              </span>
              <ChevronRight className="size-4 shrink-0 text-ink-3" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function OwnerOnly({ title }: { title: string }) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader backHref="/desk/cai-dat" title={title} />
      <EmptyState title="Chỉ chị (chủ cửa hàng) xem được phần này" />
    </div>
  );
}

/* ---------- cửa hàng ---------- */

const STORE_KEYS = [
  "store.name",
  "store.tagline",
  "store.curator_name",
  "store.curator_bio",
  "store.bank_code",
  "store.bank_account_no",
  "store.bank_account_name",
  "store.default_shipping_fee_vnd",
] as const;

const storeSchema = z.object({
  "store.name": z.string().trim().min(1, "Cửa hàng cần có tên").max(80),
  "store.tagline": z.string().max(160),
  "store.curator_name": z.string().max(80),
  "store.curator_bio": z.string().max(1500),
  "store.bank_code": z.string().max(20),
  "store.bank_account_no": z.string().regex(/^\d{0,20}$/, "Số tài khoản chỉ gồm chữ số"),
  "store.bank_account_name": z.string().max(80),
  "store.default_shipping_fee_vnd": z.string().regex(/^[\d.]*$/, "Nhập số tiền"),
});
type StoreValues = z.infer<typeof storeSchema>;

export function StoreSettingsScreen() {
  const { data, isPending, error, refetch } = useSettings();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader backHref="/desk/cai-dat" title="Cửa hàng" description="Hiện trên website và trong tin nhắn gửi khách." />
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
    STORE_KEYS.map((k) => [k, k === "store.default_shipping_fee_vnd" ? formatNumber(Number(values[k] ?? 0)) : String(values[k] ?? "")]),
  ) as StoreValues;
  const { register, handleSubmit, formState, reset } = useForm<StoreValues>({ resolver: zodResolver(storeSchema), defaultValues: defaults });
  const e = formState.errors;

  const onSubmit = handleSubmit(async (v) => {
    const out: Record<string, unknown> = {};
    for (const k of STORE_KEYS) {
      const next = k === "store.default_shipping_fee_vnd" ? Number(v[k].replace(/\D/g, "") || 0) : v[k].trim();
      if (next !== values[k]) out[k] = next;
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
        <Input label="Tên cửa hàng" error={e["store.name"]?.message} {...register("store.name")} />
        <Input label="Câu giới thiệu" hint="Một dòng dưới tên cửa hàng." {...register("store.tagline")} />
      </fieldset>
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Người chọn</SectionLabel>
        <Input label="Tên người chọn" placeholder="Vd: Chị Mai" {...register("store.curator_name")} />
        <Textarea label="Lời giới thiệu" rows={4} placeholder="Chị chọn hàng thế nào, thử bao lâu, vì sao bán…" {...register("store.curator_bio")} />
      </fieldset>
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Nhận chuyển khoản</SectionLabel>
        <div className="grid grid-cols-[7rem_1fr] gap-3">
          <Input label="Ngân hàng" placeholder="VCB" {...register("store.bank_code")} />
          <Input label="Số tài khoản" inputMode="numeric" error={e["store.bank_account_no"]?.message} {...register("store.bank_account_no")} />
        </div>
        <Input label="Tên chủ tài khoản" hint="Viết hoa không dấu, đúng như trên ngân hàng." {...register("store.bank_account_name")} />
      </fieldset>
      <fieldset disabled={!owner} className="flex flex-col gap-3">
        <SectionLabel>Giao hàng</SectionLabel>
        <Input
          label="Phí giao mặc định"
          inputMode="numeric"
          trailing="đ"
          hint="Áp khi chưa lấy được báo giá của hãng giao."
          error={e["store.default_shipping_fee_vnd"]?.message}
          {...register("store.default_shipping_fee_vnd")}
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
      <PageHeader backHref="/desk/cai-dat" title="Tài khoản của chị" />
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
    </div>
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
        backHref="/desk/cai-dat"
        title="Người phụ giúp"
        description="Người phụ xem được mọi thứ, ghi chi phí; không duyệt, không đổi cài đặt."
      />
      <Button icon={<UserPlus className="size-4" />} onClick={() => setCreating(true)} className="self-start">
        Thêm người phụ giúp
      </Button>
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

export function IntegrationsScreen() {
  const { data, isPending, error } = useIntegrations();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader backHref="/desk/cai-dat" title="Tích hợp" description="Driver nào đang chạy. «Giả lập» nghĩa là chưa nối tài khoản thật, không gửi gì ra ngoài." />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
          {data.map((i) => (
            <li key={i.kind} className="flex items-start justify-between gap-3 p-3.5">
              <div className="min-w-0">
                <p className="text-[15px] font-semibold">{i.label}</p>
                <p className="text-[13px] text-ink-2">
                  Đang dùng <code>{i.driver}</code>
                  {i.available.filter((a) => a !== i.driver).length ? ` · có sẵn: ${i.available.filter((a) => a !== i.driver).join(", ")}` : ""}
                </p>
              </div>
              <Badge tone={i.is_mock ? "warning" : "success"}>{i.is_mock ? "Giả lập" : "Thật"}</Badge>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[13px] text-ink-2">
        Đổi driver bằng biến môi trường trên máy chủ (vd <code>PAYMENTS_DRIVER=sepay</code>) rồi khởi động lại API.
      </p>
    </div>
  );
}
