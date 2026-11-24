import { describe, expect, it } from "vitest";
import { cartCount, cartKey, cartSubtotal, groupByDrop, mergeItem, parseCart, withQuantity, type CartItemInput } from "./cart";

const binh: CartItemInput = { productId: "p1", slug: "binh", name: "Bình giữ nhiệt", priceVnd: 385000, dropId: "d12", dropLabel: "Đợt 12" };
const khan: CartItemInput = { productId: "p2", slug: "khan", name: "Khăn lau", priceVnd: 89000 };

describe("giỏ hàng", () => {
  it("cộng dồn cùng món cùng đợt, tách món khác đợt", () => {
    let items = mergeItem([], binh, 1);
    items = mergeItem(items, binh, 2);
    items = mergeItem(items, { ...binh, dropId: undefined }, 1);
    expect(items).toHaveLength(2);
    expect(items[0]).toMatchObject({ key: "p1:d12:", quantity: 3 });
    expect(cartKey({ productId: "p1" })).toBe("p1:stock:");
  });

  it("đổi số lượng, về 0 thì bỏ khỏi giỏ, chặn tối đa 99", () => {
    let items = mergeItem([], binh, 150);
    expect(items[0].quantity).toBe(99);
    items = withQuantity(items, items[0].key, 4);
    expect(cartCount(items)).toBe(4);
    expect(withQuantity(items, items[0].key, 0)).toEqual([]);
  });

  it("tính tạm tính và nhóm theo đợt", () => {
    const items = mergeItem(mergeItem([], binh, 2), khan, 1);
    expect(cartSubtotal(items)).toBe(2 * 385000 + 89000);
    expect(groupByDrop(items).map((g) => g.label)).toEqual(["Đợt 12", "Hàng có sẵn"]);
  });

  it("đọc dữ liệu cũ/hỏng an toàn", () => {
    expect(parseCart(null)).toEqual([]);
    expect(parseCart("không phải json")).toEqual([]);
    expect(parseCart(JSON.stringify([{ productId: "p1", name: "A", priceVnd: 1, quantity: 2 }, { x: 1 }, { productId: "p3", name: "B", priceVnd: 1, quantity: 0 }]))).toEqual([
      { productId: "p1", name: "A", priceVnd: 1, quantity: 2, key: "p1:stock:" },
    ]);
  });
});
