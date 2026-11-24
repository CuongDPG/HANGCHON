import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Ghép className, lớp sau thắng lớp trước khi trùng nhóm (vd. `p-4` rồi `p-2` → `p-2`). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
