"use client";

import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Checkbox, Radio, Switch: dùng phần tử <input> thật (truy cập tốt, chạy với react-hook-form), chỉ đổi hình.
 */

type ChoiceProps = Omit<ComponentProps<"input">, "type"> & {
  label: ReactNode;
  /** Dòng giải thích nhỏ dưới nhãn. */
  description?: ReactNode;
};

const boxBase =
  "peer relative shrink-0 appearance-none border-[1.5px] border-line-strong bg-surface transition-colors " +
  "checked:border-accent checked:bg-accent hover:border-ink-3 checked:hover:border-accent " +
  "disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

function ChoiceRow({ id, label, description, control, disabled }: { id: string; label: ReactNode; description?: ReactNode; control: ReactNode; disabled?: boolean }) {
  return (
    <label htmlFor={id} className={cn("flex cursor-pointer items-start gap-3 py-1", disabled && "cursor-not-allowed opacity-70")}>
      <span className="relative mt-0.5 flex">{control}</span>
      <span className="min-w-0">
        <span className="block text-[15px] leading-6 text-ink">{label}</span>
        {description ? <span className="block text-[13px] text-ink-2">{description}</span> : null}
      </span>
    </label>
  );
}

export function Checkbox({ label, description, className, id, ...props }: ChoiceProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <ChoiceRow
      id={inputId}
      label={label}
      description={description}
      disabled={props.disabled}
      control={
        <>
          <input id={inputId} type="checkbox" className={cn(boxBase, "size-5 rounded-sm", className)} {...props} />
          <svg
            viewBox="0 0 16 16"
            className="pointer-events-none absolute inset-0 m-auto size-3.5 text-on-accent opacity-0 peer-checked:opacity-100"
            aria-hidden
          >
            <path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </>
      }
    />
  );
}

export function Radio({ label, description, className, id, ...props }: ChoiceProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <ChoiceRow
      id={inputId}
      label={label}
      description={description}
      disabled={props.disabled}
      control={
        <>
          <input
            id={inputId}
            type="radio"
            className={cn(boxBase, "size-5 rounded-full checked:bg-surface checked:border-[6px]", className)}
            {...props}
          />
        </>
      }
    />
  );
}

type RadioGroupProps<V extends string> = {
  name: string;
  value: V | null;
  onChange: (value: V) => void;
  options: { value: V; label: ReactNode; description?: ReactNode; disabled?: boolean }[];
  legend?: ReactNode;
  className?: string;
};

export function RadioGroup<V extends string>({ name, value, onChange, options, legend, className }: RadioGroupProps<V>) {
  return (
    <fieldset className={cn("flex flex-col gap-1", className)}>
      {legend ? <legend className="mb-1 text-sm font-medium text-ink">{legend}</legend> : null}
      {options.map((o) => (
        <Radio
          key={o.value}
          name={name}
          value={o.value}
          checked={value === o.value}
          onChange={() => onChange(o.value)}
          label={o.label}
          description={o.description}
          disabled={o.disabled}
        />
      ))}
    </fieldset>
  );
}

type SwitchProps = Omit<ComponentProps<"input">, "type" | "onChange"> & {
  label: ReactNode;
  description?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
};

/** Công tắc bật/tắt: nhãn bên trái, công tắc bên phải (kiểu danh sách cài đặt). */
export function Switch({ label, description, checked, onChange, className, id, disabled, ...props }: SwitchProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <label htmlFor={inputId} className={cn("flex cursor-pointer items-center justify-between gap-4 py-1", disabled && "cursor-not-allowed opacity-60", className)}>
      <span className="min-w-0">
        <span className="block text-[15px] text-ink">{label}</span>
        {description ? <span className="block text-[13px] text-ink-2">{description}</span> : null}
      </span>
      <span className="relative inline-flex shrink-0">
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="peer h-7 w-12 cursor-pointer appearance-none rounded-full bg-line-strong transition-colors checked:bg-accent disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          {...props}
        />
        <span className="pointer-events-none absolute left-0.5 top-0.5 size-6 rounded-full bg-surface shadow-sm transition-transform peer-checked:translate-x-5" />
      </span>
    </label>
  );
}
