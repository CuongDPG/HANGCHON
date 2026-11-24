import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { IconLink } from "./icon-button";

type PageHeaderProps = {
  title: ReactNode;
  /** Dòng nhỏ phía trên tiêu đề, vd. "Thứ tư, 25/11" hoặc "ĐỢT 12 · ĐANG MỞ". */
  eyebrow?: ReactNode;
  /** Dòng mô tả dưới tiêu đề. */
  description?: ReactNode;
  /** Có thì hiện mũi tên quay lại (chỉ mũi tên, không kèm chữ). */
  backHref?: string;
  /** Thao tác bên phải: IconButton, Button nhỏ, InlineSelect inline… */
  actions?: ReactNode;
  className?: string;
};

/** Đầu trang thống nhất cho mọi màn hình. Mỗi trang có đúng một PageHeader (một <h1>). */
export function PageHeader({ title, eyebrow, description, backHref, actions, className }: PageHeaderProps) {
  return (
    <header className={cn("flex items-start gap-2", className)}>
      {backHref ? <IconLink href={backHref} label="Quay lại" icon={<ArrowLeft />} className="-ml-2.5 shrink-0" /> : null}
      <div className={cn("min-w-0 flex-1", backHref && "pt-1.5")}>
        {eyebrow ? <p className="mb-0.5 text-[13px] font-medium text-ink-2">{eyebrow}</p> : null}
        <h1 className="text-[26px] leading-tight font-bold md:text-[30px]">{title}</h1>
        {description ? <p className="mt-1 text-[15px] text-ink-2">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-1 pt-0.5">{actions}</div> : null}
    </header>
  );
}
