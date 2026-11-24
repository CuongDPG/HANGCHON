"use client";

import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Ô nhập có nhãn, gợi ý và lỗi. Dùng được với react-hook-form: `<Input {...register("email")} error={errors.email?.message} />`.
 * React 19: `ref` là prop thường, `register()` truyền vào được.
 */

type FieldShellProps = {
  id: string;
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  className?: string;
  children: ReactNode;
};

export function FieldShell({ id, label, hint, error, required, className, children }: FieldShellProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label ? (
        <label htmlFor={id} className="text-sm font-medium text-ink">
          {label}
          {required ? <span className="ml-0.5 text-seal" aria-hidden>*</span> : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-[13px] text-seal">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-[13px] text-ink-2">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

const controlClasses =
  "w-full rounded-md border border-line-strong bg-surface px-3 text-[16px] text-ink placeholder:text-ink-3 " +
  "transition-colors hover:border-ink-3 focus:border-accent focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-accent " +
  "disabled:cursor-not-allowed disabled:bg-soft-2 disabled:text-ink-3 aria-invalid:border-seal";

type InputProps = Omit<ComponentProps<"input">, "prefix"> & {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  /** Icon hoặc chữ đứng đầu ô (vd. kính lúp). */
  leading?: ReactNode;
  /** Icon/chữ cuối ô (vd. "đ", nút xoá). */
  trailing?: ReactNode;
  wrapperClassName?: string;
};

export function Input({ label, hint, error, leading, trailing, wrapperClassName, className, id, required, ...props }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error} required={required} className={wrapperClassName}>
      <div className="relative flex items-center">
        {leading ? (
          <span className="pointer-events-none absolute left-3 flex text-ink-3 [&_svg]:size-[18px]">{leading}</span>
        ) : null}
        <input
          id={inputId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={cn(controlClasses, "h-11", leading ? "pl-10" : null, trailing ? "pr-10" : null, className)}
          {...props}
        />
        {trailing ? <span className="absolute right-3 flex text-ink-2 [&_svg]:size-[18px]">{trailing}</span> : null}
      </div>
    </FieldShell>
  );
}

type TextareaProps = ComponentProps<"textarea"> & {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  wrapperClassName?: string;
};

/** Ô nhập nhiều dòng; tự giãn theo nội dung (field-sizing) trên trình duyệt hỗ trợ. */
export function Textarea({ label, hint, error, wrapperClassName, className, id, required, rows = 3, ...props }: TextareaProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error} required={required} className={wrapperClassName}>
      <textarea
        id={inputId}
        rows={rows}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(controlClasses, "field-sizing-content min-h-24 py-2.5 leading-relaxed", className)}
        {...props}
      />
    </FieldShell>
  );
}
