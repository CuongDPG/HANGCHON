"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Button } from "./button";
import { Dialog } from "./overlay";

/**
 * Hộp xác nhận thay cho `window.confirm`:
 *   const confirm = useConfirm();
 *   if (await confirm({ title: "Loại món này?", message: "…", confirmLabel: "Loại", tone: "danger" })) { … }
 * <ConfirmProvider> đã gắn sẵn trong Providers.
 */

export type ConfirmOptions = {
  title: ReactNode;
  message?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** `danger` cho thao tác khó hoàn tác (xoá, hoàn tiền, huỷ đơn). */
  tone?: "default" | "danger";
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

const ConfirmContext = createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    pendingRef.current?.resolve(false);
    return new Promise<boolean>((resolve) => {
      const next = { ...options, resolve };
      pendingRef.current = next;
      setPending(next);
    });
  }, []);

  const settle = (ok: boolean) => {
    pendingRef.current?.resolve(ok);
    pendingRef.current = null;
    setPending(null);
  };

  return (
    <ConfirmContext value={confirm}>
      {children}
      <Dialog
        open={pending !== null}
        onClose={() => settle(false)}
        role="alertdialog"
        dismissOnBackdrop={false}
        title={pending?.title ?? ""}
        description={pending?.message}
        footer={
          <>
            <Button variant="secondary" onClick={() => settle(false)}>
              {pending?.cancelLabel ?? "Huỷ"}
            </Button>
            <Button variant={pending?.tone === "danger" ? "danger" : "primary"} onClick={() => settle(true)} autoFocus>
              {pending?.confirmLabel ?? "Đồng ý"}
            </Button>
          </>
        }
      />
    </ConfirmContext>
  );
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm phải nằm trong <ConfirmProvider> (đã có trong Providers).");
  return ctx;
}
