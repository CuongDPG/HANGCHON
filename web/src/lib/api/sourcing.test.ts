import { describe, expect, it } from "vitest";
import { isDetailFetchActive, type CandidateGallery } from "./sourcing";

const g = (status: NonNullable<CandidateGallery["detail_fetch"]>["status"] | null): CandidateGallery => ({
  candidate_id: "c1",
  title_vi: "Móc dán",
  source_url: "https://example.com/item",
  images: [],
  detail_fetch: status ? { status, at: null, error: null, note: null, image_count: null, cached: null, failed_images: null } : null,
});

describe("isDetailFetchActive", () => {
  it("chỉ đang chạy khi lượt «Lấy ảnh và chi tiết» còn xếp hàng hoặc đang chạy", () => {
    expect(isDetailFetchActive(g("queued"))).toBe(true);
    expect(isDetailFetchActive(g("running"))).toBe(true);
    expect(isDetailFetchActive(g("done"))).toBe(false);
    expect(isDetailFetchActive(g("failed"))).toBe(false);
    expect(isDetailFetchActive(g(null))).toBe(false);
    expect(isDetailFetchActive(undefined)).toBe(false);
  });
});
