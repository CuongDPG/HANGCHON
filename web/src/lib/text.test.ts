import { describe, expect, it } from "vitest";
import { matchesVi, normalizeVi, slugifyVi } from "./text";

describe("chuẩn hoá tiếng Việt", () => {
  it("bỏ dấu, đ → d, chữ thường, gộp khoảng trắng", () => {
    expect(normalizeVi("Bình GIỮ  nhiệt Đỏ")).toBe("binh giu nhiet do");
    expect(normalizeVi("  Đường   đi  ")).toBe("duong di");
    expect(normalizeVi("Khăn tắm cho bé")).toBe("khan tam cho be");
  });

  it("xử lý chuỗi tổ hợp (NFD) giống chuỗi dựng sẵn (NFC)", () => {
    expect(normalizeVi("Hộp cơm".normalize("NFD"))).toBe(normalizeVi("Hộp cơm".normalize("NFC")));
  });

  it("tìm không dấu, mọi từ đều phải khớp", () => {
    expect(matchesVi("Bình giữ nhiệt 480 ml", "binh nhiet")).toBe(true);
    expect(matchesVi("Bình giữ nhiệt 480 ml", "nhiệt bình")).toBe(true);
    expect(matchesVi("Bình giữ nhiệt 480 ml", "hop com")).toBe(false);
    expect(matchesVi(["Hộp cơm inox", null, "Bếp"], "bep inox")).toBe(true);
    expect(matchesVi("bất kỳ", "   ")).toBe(true);
  });

  it("tạo slug", () => {
    expect(slugifyVi("Bình giữ nhiệt 480 ml")).toBe("binh-giu-nhiet-480-ml");
    expect(slugifyVi("  Đèn kẹp — đọc sách! ")).toBe("den-kep-doc-sach");
  });
});
