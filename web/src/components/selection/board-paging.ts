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
