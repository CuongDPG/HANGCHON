import { Search } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Input } from "./field";

/**
 * Hàng công cụ dưới tab (tầng 3): chip phân loại dữ liệu (nhóm, kênh, khoảng thời gian) bên trái,
 * ô tìm / sắp xếp / chọn kỳ canh phải (`end`). Điện thoại: chip cuộn ngang, phần `end` xuống hàng riêng.
 *
 *   <Toolbar end={<SearchInput … />}>
 *     <Chip selected>Tất cả</Chip> <Chip>Khách quen</Chip>
 *   </Toolbar>
 */
export function Toolbar({ children, end, className }: { children?: ReactNode; end?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2 md:flex-nowrap", className)}>
      {children ? (
        <div className="-mx-4 flex min-w-0 flex-[1_1_100%] gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:flex-1 md:flex-wrap md:px-0">
          {children}
        </div>
      ) : null}
      {end ? <div className="flex min-w-0 basis-full items-center justify-end gap-2 md:ml-auto md:basis-auto md:flex-none [&>*]:min-w-0">{end}</div> : null}
    </div>
  );
}

/** Ô tìm của hàng công cụ: cao 36px như chip, canh phải, rộng 18rem trên máy tính. */
export function ToolbarSearch({ wrapperClassName, className, ...props }: Omit<ComponentProps<typeof Input>, "leading" | "type">) {
  return (
    <Input
      type="search"
      leading={<Search />}
      wrapperClassName={cn("w-full md:w-80", wrapperClassName)}
      className={cn("h-9", className)}
      {...props}
    />
  );
}
