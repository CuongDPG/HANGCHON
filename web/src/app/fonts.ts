import { Be_Vietnam_Pro, Bricolage_Grotesque } from "next/font/google";

/** Chữ thân: Be Vietnam Pro — dựng cho tiếng Việt, dấu rõ ở cỡ nhỏ. */
export const beVietnam = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-be-vietnam",
  display: "swap",
});

/** Chữ tiêu đề và con số lớn: Bricolage Grotesque (có trục opsz). */
export const bricolage = Bricolage_Grotesque({
  subsets: ["latin", "vietnamese"],
  axes: ["opsz"],
  variable: "--font-bricolage",
  display: "swap",
});
