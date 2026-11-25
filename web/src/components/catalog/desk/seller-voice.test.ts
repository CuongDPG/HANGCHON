import { describe, expect, it } from "vitest";
import { sellerAddressIssues } from "./seller-voice";

describe("sellerAddressIssues", () => {
  it("bắt «chị» người bán tự xưng và gợi ý «mình»", () => {
    expect(sellerAddressIssues("Chị đã dùng thử bao lâu?")).toEqual([{ quote: "Chị đã dùng thử bao lâu?", suggestion: "Mình đã dùng thử bao lâu?" }]);
    expect(sellerAddressIssues("Mình thử 3 tuần. Chị thấy nắp chặt, chị rất ưng.")).toEqual([
      { quote: "Chị thấy nắp chặt, chị rất ưng.", suggestion: "Mình thấy nắp chặt, mình rất ưng." },
    ]);
    expect(sellerAddressIssues("Anh chị đặt trước 20h nhé!")[0].suggestion).toBe("Bạn đặt trước 20h nhé!");
  });

  it("bỏ qua «chịu» và lời khách trong ngoặc", () => {
    expect(sellerAddressIssues("Nắp chịu nhiệt, chịu va đập.")).toEqual([]);
    expect(sellerAddressIssues("Khách nhận xét: «Chị bán hàng có tâm».")).toEqual([]);
    expect(sellerAddressIssues("Chị đọc lời khách «chị ơi ưng lắm» mà vui.")[0].suggestion).toBe("Mình đọc lời khách «chị ơi ưng lắm» mà vui.");
    expect(sellerAddressIssues(null)).toEqual([]);
  });
});
