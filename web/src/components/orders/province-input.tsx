"use client";

import { useQuery } from "@tanstack/react-query";
import { useState, type ComponentProps } from "react";
import { Input } from "@/components/ui";
import { storeOrdersApi } from "@/lib/api/orders";

/** Ô tỉnh/thành nhập tự do, có gợi ý (từ hãng giao nếu có, không thì 34 tỉnh/thành). */
export function ProvinceInput({ value, onPick, ...props }: ComponentProps<typeof Input> & { value: string; onPick: (v: string) => void }) {
  const [focus, setFocus] = useState(false);
  const q = useQuery({
    queryKey: ["store", "provinces", value],
    queryFn: () => storeOrdersApi.provinces(value),
    enabled: focus,
    staleTime: 5 * 60_000,
  });
  const hits = (q.data ?? []).filter((p) => p.name !== value).slice(0, 5);
  return (
    <div className="flex flex-col gap-1.5">
      <Input
        {...props}
        value={value}
        autoComplete="address-level1"
        onFocus={() => setFocus(true)}
        onBlur={(e) => {
          setTimeout(() => setFocus(false), 150);
          props.onBlur?.(e);
        }}
      />
      {focus && hits.length ? (
        <div className="flex flex-wrap gap-1.5" aria-label="Gợi ý tỉnh/thành">
          {hits.map((p) => (
            <button
              key={p.name}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onPick(p.name)}
              className="h-8 rounded-md border border-line-strong bg-surface px-2.5 text-[14px] hover:border-ink-3"
            >
              {p.name}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
