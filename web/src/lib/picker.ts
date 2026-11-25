/**
 * Người chọn hàng trên website. Với khách, người bán tự xưng «mình», gọi khách «bạn»; khi cần ngôi thứ ba (nhãn,
 * chú thích) thì dùng tên người chọn ở Cài đặt (`store.picker_name`), chưa đặt tên thì gọi «người chọn».
 * «Chị» chỉ là cách gọi nội bộ ở bàn làm việc, không bao giờ hiện cho khách.
 */

/** Tên trung tính API trả về khi chưa đặt `store.picker_name` (khớp `DEFAULTS` ở `api/app/modules/catalog/public.py`). */
export const DEFAULT_PICKER_NAME = "Người chọn hàng";

/** Tên người chọn đã đặt, hoặc `null` khi chưa đặt (đang là tên mặc định). */
export function pickerName(name?: string | null): string | null {
  const n = name?.trim();
  return n && n !== DEFAULT_PICKER_NAME ? n : null;
}

/** Nhãn câu người chọn trả lời: «Thu trả lời» / «Người chọn trả lời». */
export function ownerReplyLabel(name?: string | null): string {
  const n = pickerName(name);
  return n ? `${n} trả lời` : "Người chọn trả lời";
}
