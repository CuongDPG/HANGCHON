import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const base =
  "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-colors " +
  "disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-hover",
  secondary: "border border-line-strong bg-surface text-ink hover:border-ink-3 hover:bg-soft-2",
  ghost: "text-ink hover:bg-soft-2",
  danger: "bg-seal text-white hover:opacity-90 dark:text-paper",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-4 text-[15px]",
  lg: "h-13 px-5 text-base",
};

/** Lớp CSS của nút — dùng khi cần một phần tử khác trông như nút. */
export function buttonClasses({
  variant = "primary",
  size = "md",
  block = false,
  className,
}: { variant?: ButtonVariant; size?: ButtonSize; block?: boolean; className?: string } = {}) {
  return cn(base, variants[variant], sizes[size], block && "w-full", className);
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}

type CommonProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Chiếm hết bề ngang. */
  block?: boolean;
  /** Icon đứng trước chữ (vd. `<Check className="size-4" />`). */
  icon?: ReactNode;
};

export type ButtonProps = ComponentProps<"button"> & CommonProps & { loading?: boolean };

/** Nút bấm. Mặc định `type="button"` để không vô tình gửi form. */
export function Button({
  variant,
  size,
  block,
  icon,
  loading = false,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClasses({ variant, size, block, className })}
      {...props}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

export type ButtonLinkProps = ComponentProps<typeof Link> & CommonProps;

/** Liên kết trông như nút (điều hướng sang trang khác). */
export function ButtonLink({ variant, size, block, icon, className, children, ...props }: ButtonLinkProps) {
  return (
    <Link className={buttonClasses({ variant, size, block, className })} {...props}>
      {icon}
      {children}
    </Link>
  );
}
