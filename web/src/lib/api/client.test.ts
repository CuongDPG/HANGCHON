import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, NETWORK_ERROR_MESSAGE, api, buildUrl } from "./client";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  const fn = vi.fn(async () =>
    new Response(status === 204 ? null : typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "content-type": contentType },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("buildUrl", () => {
  it("bỏ tham số rỗng, lặp tham số mảng", () => {
    expect(buildUrl("/api/x", { q: "bình", page: 2, tag: ["a", "b"], empty: null, none: undefined })).toBe(
      "http://localhost:8010/api/x?q=b%C3%ACnh&page=2&tag=a&tag=b",
    );
  });
});

describe("apiFetch", () => {
  it("trả JSON và gửi body dạng JSON", async () => {
    const fetchFn = mockFetch(201, { id: "1" });
    await expect(api.post<{ id: string }>("/api/desk/x", { name: "A" })).resolves.toEqual({ id: "1" });
    const init = (fetchFn.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"name":"A"}');
  });

  it("204 trả undefined", async () => {
    mockFetch(204, null);
    await expect(api.delete("/api/desk/x/1")).resolves.toBeUndefined();
  });

  it("lấy thông báo tiếng Việt từ detail của API", async () => {
    mockFetch(400, { detail: "Đợt này đã chốt, không thêm đơn được." });
    await expect(api.post("/api/x")).rejects.toMatchObject({ status: 400, message: "Đợt này đã chốt, không thêm đơn được." });
  });

  it("gộp lỗi kiểm tra 422 của FastAPI", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "phone"], msg: "Số điện thoại chưa đúng" }] });
    await expect(api.post("/api/x")).rejects.toMatchObject({ status: 422, message: "Số điện thoại chưa đúng" });
  });

  it("không có detail thì dùng câu mặc định theo mã lỗi", async () => {
    mockFetch(401, {});
    const err = await api.get("/api/desk/auth/me").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).isUnauthorized).toBe(true);
    expect((err as ApiError).message).toMatch(/đăng nhập/);
  });

  it("API chưa chạy (Next trả 500 dạng chữ) hoặc mất mạng → lỗi kết nối", async () => {
    mockFetch(500, "Internal Server Error", "text/plain");
    await expect(api.get("/api/x")).rejects.toMatchObject({ isNetwork: true, message: NETWORK_ERROR_MESSAGE });
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    await expect(api.get("/api/x")).rejects.toMatchObject({ status: 0, isNetwork: true });
  });
});
