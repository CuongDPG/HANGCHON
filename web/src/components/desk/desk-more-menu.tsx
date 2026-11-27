"use client";

import { MoreHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { Menu, MENU_ITEM, MenuLink } from "@/components/ui/menu";
import { cn } from "@/lib/cn";

/** Một mục của menu «⋯»: liên kết (`href`) hoặc thao tác (`onSelect`). Mục `false`/`null` bị bỏ qua. */
export type DeskMoreItem =
  | { label: string; icon?: ReactNode; href: string; target?: string; separator?: boolean }
  | { label: string; icon?: ReactNode; onSelect: () => void; disabled?: boolean; danger?: boolean; separator?: boolean };

/**
 * Menu «⋯» ở cuối hàng tiêu đề desk: thao tác phụ và liên kết sang màn liên quan, để hàng tiêu đề chỉ còn
 * tối đa 1 nút chính + 2 nút khác. Không có mục nào thì không hiện.
 *
 *   <PageHeader title="…" actions={<><Button size="sm">Tạo đơn</Button><DeskMoreMenu items={[{ label: "Mẫu tin", href: "…" }]} /></>} />
 */
export function DeskMoreMenu({ items, label = "Thêm thao tác" }: { items: (DeskMoreItem | false | null | undefined)[]; label?: string }) {
  const list = items.filter(Boolean) as DeskMoreItem[];
  if (!list.length) return null;
  return (
    <Menu
      label={label}
      align="end"
      trigger={(open) => (
        <span
          className={cn(
            "inline-flex size-9 items-center justify-center rounded-md text-ink transition-colors hover:bg-soft-2 [&_svg]:size-5",
            open && "bg-soft-2",
          )}
        >
          <MoreHorizontal aria-hidden />
        </span>
      )}
    >
      {list.map((item, i) =>
        "href" in item ? (
          <MenuLink key={i} href={item.href} target={item.target} icon={item.icon} separator={item.separator}>
            {item.label}
          </MenuLink>
        ) : (
          <div key={i} role="none">
            {item.separator ? <div role="separator" className="my-1 border-t border-line" /> : null}
            <button
              type="button"
              role="menuitem"
              tabIndex={-1}
              disabled={item.disabled}
              onClick={item.onSelect}
              className={cn(MENU_ITEM, item.danger && "text-seal [&_svg]:text-seal")}
            >
              {item.icon}
              {item.label}
            </button>
          </div>
        ),
      )}
    </Menu>
  );
}
