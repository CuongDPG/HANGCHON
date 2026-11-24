"use client";

import { useSyncExternalStore } from "react";

/**
 * Giỏ hàng lưu ở trình duyệt (localStorage), không cần tài khoản. Giá trong giỏ chỉ để hiển thị nhanh —
 * trang đặt hàng luôn hỏi lại máy chủ giá thật, suất còn lại và phí giao.
 *
 *   const items = useCart();           // danh sách món
 *   const count = useCartCount();      // tổng số cái (nút giỏ ở đầu trang)
 *   addToCart({ productId, slug, name, priceVnd, dropId }, 2);
 */

export type CartItem = {
  /** `${productId}:${dropId ?? "stock"}:${variantId ?? ""}` */
  key: string;
  productId: string;
  variantId?: string;
  slug: string;
  name: string;
  priceVnd: number;
  imageUrl?: string;
  /** Có = đặt trong đợt gom; không = hàng giữ sẵn. */
  dropId?: string;
  dropLabel?: string;
  quantity: number;
};

export type CartItemInput = Omit<CartItem, "key" | "quantity">;

const STORAGE_KEY = "hc_cart_v1";
const MAX_QTY = 99;
const EMPTY: CartItem[] = [];

export function cartKey(item: Pick<CartItem, "productId" | "dropId" | "variantId">): string {
  return `${item.productId}:${item.dropId ?? "stock"}:${item.variantId ?? ""}`;
}

function clampQty(n: number): number {
  return Math.max(0, Math.min(MAX_QTY, Math.floor(Number.isFinite(n) ? n : 0)));
}

/** Đọc giỏ từ chuỗi JSON, bỏ dòng hỏng (dữ liệu cũ, sửa tay). */
export function parseCart(raw: string | null): CartItem[] {
  if (!raw) return EMPTY;
  try {
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return EMPTY;
    return data
      .filter(
        (x): x is CartItem =>
          !!x && typeof x === "object" && typeof x.productId === "string" && typeof x.name === "string" && typeof x.priceVnd === "number",
      )
      .map((x) => ({ ...x, key: cartKey(x), quantity: clampQty(x.quantity) }))
      .filter((x) => x.quantity > 0);
  } catch {
    return EMPTY;
  }
}

/** Thêm món (cộng dồn nếu đã có cùng món + cùng đợt). */
export function mergeItem(items: CartItem[], input: CartItemInput, quantity: number): CartItem[] {
  const key = cartKey(input);
  const existing = items.find((i) => i.key === key);
  if (existing) {
    return items.map((i) => (i.key === key ? { ...i, ...input, key, quantity: clampQty(i.quantity + quantity) } : i));
  }
  const q = clampQty(quantity);
  return q > 0 ? [...items, { ...input, key, quantity: q }] : items;
}

export function withQuantity(items: CartItem[], key: string, quantity: number): CartItem[] {
  const q = clampQty(quantity);
  return q === 0 ? items.filter((i) => i.key !== key) : items.map((i) => (i.key === key ? { ...i, quantity: q } : i));
}

export function cartCount(items: CartItem[]): number {
  return items.reduce((s, i) => s + i.quantity, 0);
}

export function cartSubtotal(items: CartItem[]): number {
  return items.reduce((s, i) => s + i.priceVnd * i.quantity, 0);
}

/** Nhóm theo đợt: mỗi đơn chỉ đặt trong một đợt (hàng giữ sẵn đi cùng đơn nào cũng được). */
export function groupByDrop(items: CartItem[]): { dropId: string | null; label: string; items: CartItem[] }[] {
  const groups = new Map<string, { dropId: string | null; label: string; items: CartItem[] }>();
  for (const i of items) {
    const id = i.dropId ?? "";
    if (!groups.has(id)) groups.set(id, { dropId: i.dropId ?? null, label: i.dropId ? (i.dropLabel ?? "Đợt gom") : "Hàng có sẵn", items: [] });
    groups.get(id)!.items.push(i);
  }
  return [...groups.values()];
}

// ---- kho dùng chung trong trình duyệt ----------------------------------------------------------------------------

let cache: CartItem[] | null = null;
const listeners = new Set<() => void>();

function read(): CartItem[] {
  if (cache === null) {
    cache = typeof window === "undefined" ? EMPTY : parseCart(window.localStorage.getItem(STORAGE_KEY));
  }
  return cache;
}

function write(items: CartItem[]) {
  cache = items;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* hết chỗ / chế độ riêng tư: vẫn giữ trong bộ nhớ */
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) {
      cache = parseCart(e.newValue);
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function getCart(): CartItem[] {
  return read();
}

export function addToCart(input: CartItemInput, quantity = 1) {
  write(mergeItem(read(), input, quantity));
}

export function setCartQuantity(key: string, quantity: number) {
  write(withQuantity(read(), key, quantity));
}

export function removeFromCart(key: string) {
  write(read().filter((i) => i.key !== key));
}

/** Bỏ các món đã đặt (theo key) — hoặc xoá hết nếu không truyền. */
export function clearCart(keys?: string[]) {
  write(keys ? read().filter((i) => !keys.includes(i.key)) : EMPTY);
}

export function useCart(): CartItem[] {
  return useSyncExternalStore(subscribe, read, () => EMPTY);
}

export function useCartCount(): number {
  return cartCount(useCart());
}

// ---- đơn đã đặt trên máy này (để khách mở lại trang theo dõi không cần tra) --------------------------------------

const RECENT_KEY = "hc_recent_orders_v1";
export type RecentOrder = { code: string; token: string; placedAt: string };

export function getRecentOrders(): RecentOrder[] {
  if (typeof window === "undefined") return [];
  try {
    const data: unknown = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(data) ? data.filter((x): x is RecentOrder => !!x && typeof x.code === "string" && typeof x.token === "string") : [];
  } catch {
    return [];
  }
}

export function rememberOrder(o: RecentOrder) {
  try {
    const list = [o, ...getRecentOrders().filter((x) => x.code !== o.code)].slice(0, 10);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {
    /* bỏ qua */
  }
}

export function recentToken(code: string): string | null {
  return getRecentOrders().find((o) => o.code === code)?.token ?? null;
}

const noopSubscribe = () => () => {};

/** `false` khi đang render ở máy chủ / lúc hydrate, `true` khi đã chạy trong trình duyệt (để không nháy «giỏ trống»). */
export function useIsClient(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}
