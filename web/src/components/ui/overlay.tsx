"use client";

import { X } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { IconButton } from "./icon-button";

/**
 * Sheet (trượt từ dưới lên trên điện thoại, nổi giữa màn hình trên máy tính) và Dialog (luôn ở giữa).
 * Cả hai dùng <dialog> gốc: có khoá tiêu điểm, phím Esc, top layer. Điều khiển bằng `open` + `onClose`.
 *
 *   const [open, setOpen] = useState(false);
 *   <Sheet open={open} onClose={() => setOpen(false)} title="Thêm">…</Sheet>
 */

type OverlayProps = {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  /** Hàng nút cuối (dính đáy trên điện thoại). */
  footer?: ReactNode;
  /** Ẩn tiêu đề khỏi mắt (vẫn đọc được bằng trình đọc màn hình). */
  hideTitle?: boolean;
  /** `alertdialog` cho hộp xác nhận. */
  role?: "dialog" | "alertdialog";
  /** Bấm nền mờ để đóng (mặc định bật; tắt cho hộp xác nhận). */
  dismissOnBackdrop?: boolean;
  className?: string;
  /** Bề ngang trên máy tính (Sheet): `md` 32rem (mặc định), `lg` 56rem cho nội dung dài như hộp duyệt. */
  size?: "md" | "lg";
};

function useNativeDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  // Khi trang bị ẩn do điều hướng (Activity), đóng hộp để quay lại không thấy hộp mở sẵn.
  // Hoãn tới microtask và chỉ đóng nếu hiệu ứng không được gắn lại: StrictMode (dev) gỡ rồi gắn lại hiệu ứng ngay
  // trong cùng một lượt — đóng tức thì thì Sheet mở sẵn lúc mount sẽ tự đóng.
  const attached = useRef(false);
  useLayoutEffect(() => {
    const d = ref.current;
    attached.current = true;
    return () => {
      attached.current = false;
      queueMicrotask(() => {
        if (!attached.current && d?.open) {
          d.close();
          onCloseRef.current();
        }
      });
    };
  }, []);

  return ref;
}

function OverlayFrame({
  variant,
  open,
  onClose,
  title,
  description,
  children,
  footer,
  hideTitle,
  role = "dialog",
  dismissOnBackdrop = true,
  className,
  size = "md",
}: OverlayProps & { variant: "sheet" | "dialog" }) {
  const ref = useNativeDialog(open, onClose);
  const titleId = useId();
  const descId = useId();

  return (
    <dialog
      ref={ref}
      role={role}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onClose={() => {
        if (open) onClose();
      }}
      onClick={(e) => {
        // Bấm vào nền mờ (::backdrop) thì sự kiện rơi vào chính <dialog>
        if (dismissOnBackdrop && e.target === e.currentTarget) onClose();
      }}
      className={cn(
        "m-0 max-h-none max-w-none border-0 bg-transparent p-0 text-ink backdrop:bg-overlay",
        "transition-[opacity,translate,overlay,display] transition-discrete duration-200 ease-out",
        "backdrop:transition-[opacity,overlay,display] backdrop:transition-discrete backdrop:duration-200 backdrop:opacity-0 open:backdrop:opacity-100 starting:open:backdrop:opacity-0",
        variant === "sheet" && (size === "lg" ? "md:w-[min(56rem,calc(100%-4rem))]" : "md:w-[min(32rem,calc(100%-2rem))]"),
        variant === "sheet"
          ? "fixed inset-x-0 top-auto bottom-0 w-full translate-y-full open:translate-y-0 starting:open:translate-y-full md:inset-0 md:m-auto md:h-fit md:translate-y-2 md:opacity-0 md:open:translate-y-0 md:open:opacity-100 md:starting:open:translate-y-2 md:starting:open:opacity-0"
          : "fixed inset-0 m-auto h-fit w-[min(26rem,calc(100%-2rem))] scale-[0.98] opacity-0 open:scale-100 open:opacity-100 starting:open:scale-[0.98] starting:open:opacity-0",
      )}
    >
      <div
        className={cn(
          "flex flex-col bg-surface shadow-pop",
          variant === "sheet"
            ? "max-h-[88dvh] rounded-t-lg pb-safe md:max-h-[85dvh] md:rounded-md md:pb-0"
            : "max-h-[85dvh] rounded-md",
          className,
        )}
      >
        {variant === "sheet" ? <div aria-hidden className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-line-strong md:hidden" /> : null}
        <div className={cn("flex items-start gap-3 px-5 pt-4", hideTitle && "sr-only")}>
          <div className="min-w-0 flex-1 pt-1">
            <h2 id={titleId} className="text-lg font-bold">
              {title}
            </h2>
            {description ? (
              <p id={descId} className="mt-1 text-[15px] text-ink-2">
                {description}
              </p>
            ) : null}
          </div>
          {role === "dialog" ? <IconButton label="Đóng" icon={<X />} size="sm" onClick={onClose} className="-mr-2 shrink-0" /> : null}
        </div>
        {children ? <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-3 pb-5">{children}</div> : <div className="h-4" />}
        {footer ? (
          <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-line px-5 py-3 max-md:[&>*]:flex-1">{footer}</div>
        ) : null}
      </div>
    </dialog>
  );
}

export function Sheet(props: OverlayProps) {
  return <OverlayFrame variant="sheet" {...props} />;
}

export function Dialog(props: OverlayProps) {
  return <OverlayFrame variant="dialog" {...props} />;
}
