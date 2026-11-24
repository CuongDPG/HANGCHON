import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Variant = "ghost" | "secondary" | "primary";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  ghost: "text-ink hover:bg-soft-2",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-soft-2",
  primary: "bg-accent text-on-accent hover:bg-accent-hover",
};
const sizes: Record<Size, string> = { sm: "size-9", md: "size-11" };

function classes(variant: Variant, size: Size, className?: string) {
  return cn(
    "relative inline-flex shrink-0 items-center justify-center rounded-md transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-5",
    variants[variant],
    sizes[size],
    className,
  );
}

type Common = {
  /** Bắt buộc: tên đọc cho trình đọc màn hình (vd. "Quay lại", "Giỏ hàng"). */
  label: string;
  icon: ReactNode;
  variant?: Variant;
  size?: Size;
  /** Số nhỏ ở góc (vd. số món trong giỏ). 0 hoặc không truyền thì ẩn. */
  count?: number;
};

function CountDot({ count }: { count?: number }) {
  if (!count) return null;
  return (
    <span className="absolute -right-0.5 -top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-seal px-1 text-[11px] font-bold leading-none text-white tabular-nums dark:text-paper">
      {count > 99 ? "99+" : count}
    </span>
  );
}

export function IconButton({
  label,
  icon,
  variant = "ghost",
  size = "md",
  count,
  className,
  type = "button",
  ...props
}: Omit<ComponentProps<"button">, "children"> & Common) {
  return (
    <button type={type} aria-label={label} title={label} className={classes(variant, size, className)} {...props}>
      {icon}
      <CountDot count={count} />
    </button>
  );
}

export function IconLink({
  label,
  icon,
  variant = "ghost",
  size = "md",
  count,
  className,
  ...props
}: Omit<ComponentProps<typeof Link>, "children"> & Common) {
  return (
    <Link aria-label={label} title={label} className={classes(variant, size, className)} {...props}>
      {icon}
      <CountDot count={count} />
    </Link>
  );
}
