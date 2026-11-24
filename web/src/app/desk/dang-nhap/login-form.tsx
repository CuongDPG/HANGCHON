"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, LogIn } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { useLogin, useSession } from "@/lib/api/auth";

const schema = z.object({
  email: z.string().trim().min(1, "Nhập email.").pipe(z.email("Email chưa đúng dạng.")),
  password: z.string().min(1, "Nhập mật khẩu."),
});
type FormValues = z.infer<typeof schema>;

/** Chỉ cho quay về trong /desk (chặn chuyển hướng ra ngoài). */
function safeNext(next: string | null): string {
  return next && next.startsWith("/desk") && !next.startsWith("//") ? next : "/desk";
}

export function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const { status } = useSession();
  const login = useLogin();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  // Đã đăng nhập sẵn thì vào thẳng bàn làm việc
  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  const onSubmit = handleSubmit((values) => {
    login.mutate(values, { onSuccess: () => router.replace(next) });
  });

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {login.error ? (
        <p role="alert" className="flex items-start gap-2 rounded-md bg-seal-wash px-3 py-2.5 text-[14px] text-seal">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          {login.error.message}
        </p>
      ) : null}
      <Input label="Email" type="email" autoComplete="username" inputMode="email" error={errors.email?.message} {...register("email")} />
      <Input label="Mật khẩu" type="password" autoComplete="current-password" error={errors.password?.message} {...register("password")} />
      <Button type="submit" block size="lg" loading={login.isPending} icon={<LogIn className="size-4" />} className="mt-1">
        Đăng nhập
      </Button>
    </form>
  );
}
