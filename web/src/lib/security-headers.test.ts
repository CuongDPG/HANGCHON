import { describe, expect, it } from "vitest";

import nextConfig from "../../next.config";
import { SECURITY_HEADERS, SECURITY_HEADERS_SOURCE } from "./security-headers";

describe("header bảo mật", () => {
  it("next.config gắn header cho mọi trang, không đụng /api", async () => {
    const rules = (await nextConfig.headers?.()) ?? [];
    const rule = rules.find((r) => r.source === SECURITY_HEADERS_SOURCE);
    expect(rule?.headers).toEqual(SECURITY_HEADERS);
    const re = new RegExp(`^${SECURITY_HEADERS_SOURCE}$`);
    expect(re.test("/desk/don-hang")).toBe(true);
    expect(re.test("/api/files/public/x.jpg")).toBe(false);
  });

  it("chặn nhúng khung và đoán kiểu nội dung", () => {
    const get = (k: string) => SECURITY_HEADERS.find((h) => h.key === k)?.value ?? "";
    expect(get("X-Frame-Options")).toBe("DENY");
    expect(get("Content-Security-Policy")).toContain("frame-ancestors 'none'");
    expect(get("X-Content-Type-Options")).toBe("nosniff");
  });
});
