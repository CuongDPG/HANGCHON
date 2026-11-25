import { describe, expect, it } from "vitest";
import { DEFAULT_PICKER_NAME, ownerReplyLabel, pickerName } from "./picker";

describe("picker", () => {
  it("tên mặc định hoặc để trống coi như chưa đặt tên", () => {
    expect(pickerName(DEFAULT_PICKER_NAME)).toBeNull();
    expect(pickerName("  ")).toBeNull();
    expect(pickerName(null)).toBeNull();
    expect(pickerName(" Thu ")).toBe("Thu");
  });

  it("nhãn trả lời dùng tên người chọn, không bao giờ «chị»", () => {
    expect(ownerReplyLabel("Thu")).toBe("Thu trả lời");
    expect(ownerReplyLabel(undefined)).toBe("Người chọn trả lời");
    expect(ownerReplyLabel(DEFAULT_PICKER_NAME)).toBe("Người chọn trả lời");
  });
});
