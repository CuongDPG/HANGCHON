/**
 * Chuẩn hoá tiếng Việt để tìm kiếm: bỏ dấu, đ → d, chữ thường, gộp khoảng trắng.
 * "Bình GIỮ  nhiệt Đỏ" → "binh giu nhiet do".
 */
export function normalizeVi(input: string): string {
  return input
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Khớp tìm kiếm không dấu: mọi từ trong `query` đều phải có trong `haystack` (không cần đúng thứ tự).
 * Ô tìm rỗng thì khớp tất cả.
 */
export function matchesVi(haystack: string | Array<string | null | undefined>, query: string): boolean {
  const terms = normalizeVi(query).split(" ").filter(Boolean);
  if (terms.length === 0) return true;
  const text = normalizeVi(Array.isArray(haystack) ? haystack.filter(Boolean).join(" ") : haystack);
  return terms.every((t) => text.includes(t));
}

/** Tạo slug từ tên tiếng Việt: "Bình giữ nhiệt 480 ml" → "binh-giu-nhiet-480-ml". */
export function slugifyVi(input: string): string {
  return normalizeVi(input)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
