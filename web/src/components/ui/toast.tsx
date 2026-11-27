"use client";

import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/cn";

/**
 * Thông báo nhỏ (toast). Gọi ở bất kỳ đâu phía client, không cần hook:
 *   notifySuccess("Đã lưu");   notifyError(err)   // err: ApiError | Error | chuỗi
 * <Toaster /> đã gắn sẵn trong Providers.
 */

type ToastTone = "success" | "error" | "info";
/** Nút một chạm trong thông báo (vd. «Chuyển sang Tự xếp»); bấm xong tự đóng thông báo. */
export type ToastAction = { label: string; onClick: () => void };
type Toast = { id: number; tone: ToastTone; message: string; action?: ToastAction };

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();
const EMPTY: Toast[] = [];

function emit() {
  listeners.forEach((l) => l());
}

function push(tone: ToastTone, message: string, durationMs: number, action?: ToastAction) {
  const id = nextId++;
  toasts = [...toasts.slice(-2), { id, tone, message, action }];
  emit();
  setTimeout(() => dismissToast(id), durationMs);
  return id;
}

export function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function notifySuccess(message: string) {
  return push("success", message, 3500);
}

/** Thông báo trung tính, có thể kèm một nút thao tác. */
export function notifyInfo(message: string, action?: ToastAction) {
  return push("info", message, action ? 6000 : 3500, action);
}

export function notifyError(error: unknown) {
  const message = typeof error === "string" ? error : errorMessage(error);
  return push("error", message, 6000);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function Toaster() {
  const items = useSyncExternalStore(
    subscribe,
    () => toasts,
    () => EMPTY,
  );
  const ref = useRef<HTMLDivElement>(null);
  const lastTopId = items.at(-1)?.id;

  // Đặt vùng thông báo vào top layer (popover) để nổi cả trên Sheet/Dialog đang mở.
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof el.showPopover !== "function") return;
    if (lastTopId === undefined) {
      if (el.matches(":popover-open")) el.hidePopover();
      return;
    }
    if (el.matches(":popover-open")) el.hidePopover();
    el.showPopover();
  }, [lastTopId]);

  return (
    <div
      ref={ref}
      popover="manual"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-0 bottom-auto m-0 h-auto overflow-visible flex w-full max-w-none flex-col items-center gap-2 border-0 bg-transparent p-3 pt-[max(12px,env(safe-area-inset-top))]"
    >
      {items.map((t) => (
        <div
          key={t.id}
          role={t.tone === "error" ? "alert" : "status"}
          className={cn(
            "pointer-events-auto flex w-full max-w-md animate-toast-in items-start gap-3 rounded-md border bg-surface px-4 py-3 text-sm shadow-pop",
            t.tone === "error" ? "border-seal/40" : "border-line",
          )}
        >
          {t.tone === "error" ? (
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-seal" aria-hidden />
          ) : t.tone === "info" ? (
            <Info className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
          ) : (
            <CircleCheck className="mt-0.5 size-4 shrink-0 text-auto" aria-hidden />
          )}
          <p className="min-w-0 flex-1 text-ink">{t.message}</p>
          {t.action ? (
            <button
              type="button"
              onClick={() => {
                t.action?.onClick();
                dismissToast(t.id);
              }}
              className="-my-0.5 shrink-0 rounded-md px-1.5 py-0.5 font-semibold text-accent hover:bg-accent-wash"
            >
              {t.action.label}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => dismissToast(t.id)}
            className="-m-1 rounded-md p-1 text-ink-3 hover:text-ink"
            aria-label="Đóng thông báo"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  );
}
