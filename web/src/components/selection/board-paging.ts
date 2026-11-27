import type { BoardSortParam } from "@/lib/api/selection";

/** Phân trang dần trên Bàn chọn: mỗi cột vẽ trước `BOARD_PAGE` thẻ, bấm «Xem thêm» vẽ thêm chừng ấy. */
export const BOARD_PAGE = 30;

export function pageOf<T>(cards: T[], shown: number, total = cards.length) {
  const visible = cards.slice(0, Math.max(0, shown));
  return {
    visible,
    /** Thẻ đã tải về nhưng chưa vẽ. */
    more: cards.length - visible.length,
    /** Thẻ máy chủ chưa gửi (cột vượt trần tải của bàn chọn). */
    notLoaded: Math.max(0, total - cards.length),
  };
}

/** Cách xếp thẻ trong cột. `manual` = «Tự xếp» (thứ tự chị kéo), mặc định, không ghi lên URL. */
export type BoardSort = BoardSortParam;

export const BOARD_SORT_OPTIONS: { value: BoardSort; label: string }[] = [
  { value: "manual", label: "Tự xếp" },
  { value: "newest", label: "Mới nhất" },
  { value: "oldest", label: "Cũ nhất" },
];

/** Khoá localStorage nhớ cách xếp trên từng máy. */
export const BOARD_SORT_KEY = "hangchon.board-sort";

const TO_PARAM: Record<BoardSort, string | null> = { manual: null, newest: "moi", oldest: "cu" };

/** `?xep=moi|cu` → cách xếp; thiếu hoặc lạ thì `null` (để nơi gọi lấy giá trị nhớ trên máy). */
export function sortFromParam(v: string | null | undefined): BoardSort | null {
  if (v === "moi") return "newest";
  if (v === "cu") return "oldest";
  return null;
}

export function sortParam(sort: BoardSort): string | null {
  return TO_PARAM[sort];
}

export function isBoardSort(v: unknown): v is BoardSort {
  return v === "manual" || v === "newest" || v === "oldest";
}
