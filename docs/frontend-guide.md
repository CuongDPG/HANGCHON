# Hướng dẫn frontend (`web/`)

Đọc kèm [ARCHITECTURE.md](ARCHITECTURE.md) mục 8. Xem tận mắt mọi component: `http://localhost:3010/desk/kit`.

## 1. Nền tảng đã chọn

| Thứ | Bản | Ghi chú |
|---|---|---|
| Next.js | 16.4 (App Router, Turbopack) | `cacheComponents` + `partialPrefetching` bật (mặc định của bản 16.4) |
| React | 19.3 | `ref` là prop thường; `<Activity>` giữ trang đã rời |
| Tailwind CSS | 4.3 | Cấu hình trong `src/app/globals.css` (không có `tailwind.config`) |
| TypeScript | 5.9, `strict` | `bun run typecheck` = `next typegen && tsc --noEmit` |
| Dữ liệu | TanStack Query 5, zod 4, react-hook-form 7 | |
| Icon | lucide-react | luôn `aria-hidden` khi đi kèm chữ |
| Test | Vitest 5 (tiện ích), Playwright 1.62 (khói) | Playwright 1.62 dùng Chromium 1234 đã có sẵn trên máy |

Tài liệu Next.js đúng bản nằm ở `web/node_modules/next/dist/docs/` — **đọc ở đó**, bản 16.4 khác nhiều so với trí nhớ (xem `web/AGENTS.md`).

## 2. Thêm một màn hình

### Bàn làm việc (`/desk/...`)

1. Mọi khu đã có trong `src/lib/desk-nav.ts` và đã có trang giữ chỗ. **Không sửa `desk-nav.ts`** trừ khi thêm khu mới hẳn.
2. Thay nội dung `src/app/desk/(app)/<khu>/page.tsx`. Trang con thêm ở `src/app/desk/(app)/<khu>/<…>/page.tsx`
   (vd. `/desk/san-hang/[id]`). Nhóm `(app)` đã có khung (điều hướng, chặn đăng nhập, nút «Nói với AI», `error.tsx`).
3. Gọi API qua `src/lib/api/<module>.ts` (tên module như backend: `sourcing`, `selection`, `orders`…), trạng thái máy chủ dùng TanStack Query.
4. Component riêng của module đặt ở `src/components/<module>/`. Thứ dùng chung nhiều module → `src/components/ui/` (và bày thêm ở `/desk/kit`).

Trang desk là Client Component (dữ liệu sau đăng nhập, gọi từ trình duyệt):

```tsx
// src/app/desk/(app)/duyet/page.tsx
import { ApprovalsScreen } from "@/components/control/approvals-screen";
export const metadata = { title: "Chờ duyệt" };
export default function Page() {
  return <ApprovalsScreen />;
}
```

```tsx
// src/components/control/approvals-screen.tsx
"use client";
import { PageHeader, SkeletonList, EmptyState } from "@/components/ui";
import { useApprovals } from "@/lib/api/control";

export function ApprovalsScreen() {
  const { data, isPending, error } = useApprovals({ status: "pending" });
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Chờ duyệt" />
      {isPending ? <SkeletonList /> : error ? <EmptyState tone="error" title="Chưa tải được" description={error.message} /> : …}
    </div>
  );
}
```

### Website cho khách (`/...`)

1. Trang ở `src/app/(store)/<đường-dẫn>/page.tsx`, đã có trang giữ chỗ cho mọi route trong bản đồ (mục 6).
2. Mặc định là **Server Component**, lấy dữ liệu bằng `api.get(...)` (không cần cookie). Có dữ liệu sản phẩm thì kèm JSON-LD `Product`/`Offer` (e10).
3. Phần tương tác (giỏ, chọn số lượng, ô hỏi trợ lý) tách thành Client Component nhỏ.
4. Với `cacheComponents`: đọc `params`, `searchParams`, `cookies()` hoặc gọi API không cache là **dữ liệu theo request** → đặt trong
   `<Suspense fallback={…}>` (xem mẫu ở `src/app/(store)/san-pham/[slug]/ho-so-chon/page.tsx`) hoặc cache bằng `"use cache"`. Build sẽ báo lỗi nếu quên.
   Client Component dùng `usePathname`/`useSearchParams` ở route động cũng phải nằm trong `<Suspense>` (xem `store-nav-links.tsx`).

### Quy ước chung

- Mỗi trang đúng một `PageHeader` (một `<h1>`). Nút quay lại chỉ là mũi tên (`backHref`).
- Trang gốc bọc nội dung trong `<div className="flex flex-col gap-4">` (hoặc `gap-6`); khung đã lo lề và khoảng chừa cho thanh điều hướng.
- Thiết kế ở **390px trước**, rồi nới bằng `md:` (768px) — đây cũng là mốc điều hướng chuyển từ thanh dưới sang cột trái/hàng menu trên.
- Chỉ dùng token màu (mục 4). Bảng màu mặc định của Tailwind đã tắt: `bg-red-500` sẽ không có tác dụng.
- Không dùng `alert/confirm/prompt` và không dùng `<select>` thuần: dùng `useConfirm()`, `notifySuccess/notifyError`, `InlineSelect`.
- Tiền luôn qua `<Money>`/`formatVnd` (số nguyên VND). Ngày giờ qua `<DateTime>`/`format*` (giờ Việt Nam).
- Tìm kiếm phía client dùng `matchesVi(text, query)` (không dấu, đ → d).
- Đặt tên: route tiếng Việt không dấu gạch nối (`/desk/san-hang`, `/don/[code]`); file kebab-case tiếng Anh
  (`approvals-screen.tsx`); component PascalCase tiếng Anh; chuỗi giao diện tiếng Việt; gọi người dùng là «chị» ở desk, «bạn» ở website.
- Activity (Next 16): rời trang thì trang **được giữ lại ẩn**, không bị huỷ. Sheet/Dialog trong `components/ui` đã tự đóng khi trang bị ẩn;
  menu/popup tự viết thì đóng trong cleanup của `useLayoutEffect`. Đăng xuất tải lại hẳn trang (`useLogout` đã làm).

## 3. Gọi API

Tất cả nằm trong `src/lib/api/`:

| File | Dùng khi |
|---|---|
| `client.ts` | `api.get/post/patch/put/delete`, `ApiError`, `Paginated<T>`, `errorMessage(err)`. Chạy được ở Server và Client Component. |
| `server.ts` | `serverFetch(path)` — Server Component cần cookie đăng nhập (đặt trong `<Suspense>`). |
| `auth.ts` | `useSession()`, `useLogin()`, `useLogout()`, kiểu `SessionUser`. |
| `<module>.ts` | Mỗi module backend một file: kiểu dữ liệu + hàm gọi + hook TanStack Query. |

- Trình duyệt gọi `/api/...` cùng origin; `next.config.ts` chuyển tiếp sang `API_ORIGIN` (mặc định `http://localhost:8010`). Cookie httpOnly tự đi kèm.
  Rewrites tính lúc build → bản chạy thật phải có `API_ORIGIN` khi `next build`.
- Lỗi luôn là `ApiError` với `message` tiếng Việt: lấy `detail` của API (chuỗi, hoặc mảng lỗi 422), không có thì câu mặc định theo mã.
  `isNetwork` = không tới được máy chủ (kể cả khi Next trả 500 dạng chữ vì API chưa chạy). `isUnauthorized` = 401.
- Mutation lỗi tự hiện toast (`notifyError`). Màn hình tự hiện lỗi tại chỗ thì đặt `meta: { silentError: true }`.
- Query không thử lại lỗi 4xx; lỗi mạng/5xx thử lại 1 lần.
- `Paginated<T>` = `{ items: T[]; total: number }` (khớp `Paginated[T]` của PMAI). Backend thêm trường thì bổ sung ở đây.

Mẫu một file module:

```ts
// src/lib/api/control.ts
"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Paginated } from "./client";

export type ApprovalItem = { id: string; action: string; title: string; status: "pending" | "approved" | "returned"; created_at: string };

export const controlKeys = { approvals: (q: object) => ["control", "approvals", q] as const };

export function useApprovals(query: { status?: string; page?: number }) {
  return useQuery({ queryKey: controlKeys.approvals(query), queryFn: () => api.get<Paginated<ApprovalItem>>("/api/desk/approvals", { query }) });
}

export function useApprove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<ApprovalItem>(`/api/desk/approvals/${id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["control", "approvals"] }),
  });
}
```

Form: `react-hook-form` + `zodResolver(schema)`; `Input` nhận thẳng `{...register("x")}` và `error={errors.x?.message}` (mẫu: `src/app/desk/dang-nhap/login-form.tsx`).

Đăng nhập: khung `(app)` gọi `GET /api/desk/auth/me` — 401 thì chuyển `/desk/dang-nhap?next=…`, lỗi mạng thì báo «Chưa kết nối được máy chủ» + Thử lại.
Trang con vẫn được render (ẩn, `inert`) trong lúc chờ phiên, nên hook dữ liệu của trang có thể chạy trước; API tự chặn 401. Người dùng hiện tại: `useSession().user`.

## 4. Hệ thiết kế «Chàm»

Token khai báo một lần trong `src/app/globals.css` (sáng, tối, theo máy). Dùng qua lớp Tailwind:

| Token | Lớp | Dùng cho |
|---|---|---|
| `paper` | `bg-paper` | nền trang `#F6F6F2` |
| `surface` | `bg-surface` | thẻ, ô nhập, thanh điều hướng |
| `soft`, `soft-2` | `bg-soft`, `bg-soft-2` | nền phụ `#E1E3EC`; hover, nền chờ ảnh |
| `line`, `line-strong` | `border-line`, `border-line-strong` | đường kẻ; viền ô nhập |
| `ink`, `ink-2`, `ink-3` | `text-ink`… | chữ chính `#1C1D22`; chữ phụ; chữ mờ (chỉ gợi ý) |
| `accent`, `accent-hover`, `accent-wash`, `on-accent` | `bg-accent text-on-accent` | chàm `#2E3F8F`: hành động chính, mục đang chọn |
| `seal`, `seal-wash` | | đỏ son: «Chị quyết», con dấu, lỗi (bí danh `danger`) |
| `review`, `review-wash` | | vàng nâu: «AI làm, chị duyệt», cảnh báo (bí danh `warning`) |
| `auto`, `auto-wash` | | xanh cổ vịt: «AI tự làm», thành công (bí danh `success`) |

- Chữ: `font-sans` (Be Vietnam Pro, mặc định) và `font-display` (Bricolage Grotesque — tiêu đề, con số lớn). `h1–h4` tự dùng `font-display`, giãn 0.01em.
  Cỡ thường dùng: tiêu đề trang 26/30px (do `PageHeader`), khối 20px, thẻ 15px đậm, thân 15–16px, phụ 13–14px.
- Góc: `rounded-md` = 4px là chuẩn; `rounded-sm` 2px; `rounded-lg` 6px (mép sheet); `rounded-full` chỉ cho dấu, chấm, công tắc.
- Khoảng cách: bội số 4px. Kích thước bố cục: `h-header` 56px, `h-tabbar` 64px, `w-sidebar` 248px, `max-w-page` 1120px, `max-w-prose` 40rem.
- Vùng an toàn điện thoại: `pb-safe`, `pt-safe`.
- Giao diện tối: tự theo máy; chọn tay bằng `useThemePreference()` (`src/lib/use-theme.ts`). Muốn xem một khối ở giao diện khác: đặt `data-theme="dark"` lên khối đó.
  `dark:` chỉ dùng khi thật cần (ảnh, minh hoạ).

## 5. Bộ component (`@/components/ui`)

Nhập từ một chỗ: `import { Button, Card, Money } from "@/components/ui";`

| Component | Ví dụ |
|---|---|
| `Button`, `ButtonLink`, `buttonClasses()` | `<Button variant="primary\|secondary\|ghost\|danger" size="sm\|md\|lg" loading block icon={<Check className="size-4" />}>Duyệt</Button>` · `<ButtonLink href="/dot">Xem đợt</ButtonLink>` |
| `IconButton`, `IconLink` | `<IconButton label="Lọc" icon={<SlidersHorizontal />} />` · `<IconLink href="/gio-hang" label="Giỏ hàng" icon={<ShoppingBag />} count={2} />` (bắt buộc `label`) |
| `Input`, `Textarea` | `<Input label="Số điện thoại" hint="…" error={errors.phone?.message} leading={<Search />} trailing="đ" {...register("phone")} />` |
| `InlineSelect` | `<InlineSelect label="Hãng giao" value={v} onChange={setV} options={[{ value: "ghn", label: "GHN", hint: "22.000đ" }]} />` · `appearance="inline"` để chen trong câu |
| `Checkbox`, `Radio`, `RadioGroup`, `Switch` | `<Checkbox label="Chỉ hàng Nhật" />` · `<RadioGroup name="pay" value={v} onChange={setV} options={[…]} />` · `<Switch label="Tự đăng" checked={on} onChange={setOn} />` |
| `Segmented` | `<Segmented aria-label="Mức tự chủ" value={lv} onChange={setLv} options={[{value:"auto",label:"Tự làm"},…]} />` (2–4 lựa chọn ngắn) |
| `Tabs` | `<Tabs aria-label="Trạng thái" value={t} onChange={setT} items={[{ value: "cho", label: "Chờ thanh toán", count: 3 }]} />` |
| `Chip`, `ChipRow` | `<ChipRow><Chip selected count={38}>Tất cả</Chip>…</ChipRow>` (bộ lọc bấm được) |
| `Badge` | `<Badge tone="neutral\|accent\|success\|warning\|danger\|outline">Chờ chuyển khoản</Badge>` (nhãn tĩnh) |
| `LevelTag`, `LevelMark`, `LEVEL_LABELS` | `<LevelTag level="owner\|review\|auto" />` · `<LevelTag level="review">Chờ duyệt</LevelTag>` — vuông đỏ son / nửa tròn vàng nâu / tròn cổ vịt |
| `Seal` | `<Seal chosen={1} total={24} size={48} />` — con dấu «ĐÃ CHỌN 1/24», đi theo món hàng ở mọi nơi |
| `Card`, `CardLink`, `CardHeader`, `SectionLabel` | `<Card tone="default\|soft\|accent\|danger\|plain">` · `<CardHeader title="…" aside={<LevelTag … />} />` · `<SectionLabel>HÀNG ĐANG VỀ</SectionLabel>` |
| `Sheet`, `Dialog` | `<Sheet open={o} onClose={() => setO(false)} title="Lọc" footer={<Button>Áp dụng</Button>}>…</Sheet>` (dưới lên ở điện thoại, giữa màn hình ở máy tính) |
| `useConfirm()` | `if (await confirm({ title: "Loại món này?", message: "…", confirmLabel: "Loại", tone: "danger" })) …` |
| `notifySuccess`, `notifyError` | `notifySuccess("Đã lưu")` · `notifyError(err)` (nhận `ApiError`, `Error` hoặc chuỗi) |
| `ProgressBar`, `ScoreBar` | `<ProgressBar value={86} max={120} label="86 trên 120 suất" />` · `<ScoreBar label="Chất lượng" score={22} max={25} />` |
| `Skeleton`, `SkeletonList` | `<Skeleton className="h-5 w-40" />` · `<SkeletonList rows={3} />` |
| `EmptyState` | `<EmptyState icon={<Search />} title="Chưa có ứng viên" description="…" action={<Button>Ra đề</Button>} tone="error" />` |
| `PageHeader` | `<PageHeader eyebrow="Thứ tư, 25/11" title="Hôm nay" description="…" backHref="/desk" actions={…} />` |
| `ImageBox` | `<ImageBox src={url} alt="…" ratio="1/1\|4/5\|3/4\|4/3\|16/9" placeholder="Ảnh chị chụp" overlay={<Seal … />} priority />` |
| `Money` | `<Money value={385000} />` → 385.000đ · `compact` → 3,4 tr · `strike` |
| `DateTime`, `useNow()` | `<DateTime value={iso} format="date\|dayMonth\|time\|dateTime\|weekday\|relative" />` |
| `StatTile` | `<div className="grid grid-cols-3 gap-2"><StatTile value="9" label="đơn mới" href="/desk/don-hang" /></div>` |
| `DataList` | `<DataList items={[{ label: "Tạm tính", value: <Money value={385000} /> }, { label: "Tổng", value: …, strong: true }]} />` |
| `Timeline` | `<Timeline items={[{ title: "Rời kho Osaka", meta: "04/12", status: "done\|current\|todo" }]} />` |

Tiện ích (`src/lib`): `format.ts` (`formatVnd`, `formatVndCompact`, `formatNumber`, `formatPercent`, `formatDate`, `formatDayMonth`, `formatTime`,
`formatDateTime`, `formatWeekday`, `formatRelative`), `text.ts` (`normalizeVi`, `matchesVi`, `slugifyVi`), `cn.ts` (ghép className, lớp sau thắng).

Khung: `components/layout/brand.tsx` (`Brand`, `BrandMark`), `components/store/*` (đầu trang, thanh dưới, chân trang, `StorePlaceholder`),
`components/desk/*` (`DeskShell`, `MoreSheet`, `CommandButton`, `DeskPlaceholder`).

## 6. Bản đồ route

### Website cho khách — `src/app/(store)/`

| Route | Màn hình | Chức năng |
|---|---|---|
| `/` | Kệ hàng đã chọn (trang chủ, hướng B) | e1, e2 |
| `/san-pham/[slug]` | Trang sản phẩm | e1, e2, e7, e8 |
| `/san-pham/[slug]/ho-so-chon` | Hồ sơ chọn | e2 |
| `/dot`, `/dot/[slug]` | Đợt gom đơn, chi tiết đợt | e3 |
| `/gio-hang`, `/dat-hang` | Giỏ, đặt hàng một trang | e4 |
| `/don`, `/don/[code]` | Tra cứu đơn, theo dõi đơn | e5, g5 |
| `/nho-tim` | Nhờ chị tìm | e9 |
| `/ve-nguoi-chon` | Về người chọn | — |
| `/hoi` | Hỏi trợ lý | e7 |

Điều hướng (thanh dưới điện thoại / menu trên máy tính): `src/lib/store-nav.ts` — Kệ hàng · Đợt gom · Nhờ tìm · Đơn · Người chọn.

### Bàn làm việc — `src/app/desk/`

Nguồn duy nhất: `src/lib/desk-nav.ts` (`DESK_PRIMARY_NAV`, `DESK_MORE_NAV`, `findDeskNav`).

| Route | Khu | Chức năng |
|---|---|---|
| `/desk` | Hôm nay | i1 |
| `/desk/san-hang` | Săn hàng (+ hồ sơ thẩm định) | a1–a7, b1–b7 |
| `/desk/ban-chon` | Bàn chọn | c1–c6 |
| `/desk/noi-dung` | Nội dung, lịch đăng | f1–f8 |
| `/desk/khach` | Khách, hộp thư | h1–h8 |
| `/desk/don-hang` | Đơn hàng *(Thêm)* | g1–g9 |
| `/desk/nguon-cung` | Nguồn cung *(Thêm)* | d1–d7 |
| `/desk/duyet` | Chờ duyệt *(Thêm)* | i2 |
| `/desk/tu-chu` | Mức tự chủ *(Thêm)* | i3, k2 |
| `/desk/nhat-ky-ai` | Nhật ký AI *(Thêm)* | i4, k3 |
| `/desk/bao-cao` | Báo cáo *(Thêm)* | i5, f7 |
| `/desk/so-sach` | Sổ sách *(Thêm)* | k1, k5 |
| `/desk/san-pham` | Sản phẩm *(Thêm)* | e1–e3, e6, e8–e10, g8 |
| `/desk/cai-dat` | Cài đặt *(Thêm)* | k4 |
| `/desk/dang-nhap` | Đăng nhập (ngoài khung, không cần đăng nhập) | — |
| `/desk/kit` | Trưng bày hệ thiết kế (ngoài khung, không cần đăng nhập) | — |
| `/desk/manifest.webmanifest` | Manifest PWA (phạm vi `/desk`) | — |

PWA: manifest ở `src/app/desk/manifest.webmanifest/route.ts`, icon ở `public/desk/` và `src/app/apple-icon.png`, favicon `src/app/icon.svg`.
Chưa có service worker (không chạy ngoại tuyến).

## 7. Kiểm tra

```bash
cd web
bun run typecheck && bun run lint && bun run test   # = scripts/check.sh web
bun run build                                       # tắt `bun dev` trước
bun run e2e                                         # Playwright khói: /, /desk/dang-nhap, /desk/kit ở 390px và 1280px
E2E_SHOTS=1 bun run e2e                             # kèm ảnh chụp ở test-results/shots/
```

Bài khói chạy được khi API chưa chạy: lỗi tải `/api/*` được bỏ qua, nhưng trang phải hiện trạng thái trống/lỗi tử tế,
không lỗi console, không tràn ngang ở 390px. Thêm màn hình quan trọng thì thêm một dòng vào `e2e/smoke.spec.ts`.
Lưu ý Activity: trang đã rời vẫn nằm ẩn trong DOM, nên khi đếm phần tử trong Playwright hãy giới hạn trong vùng đang hiện (vd. `getByRole("main")`, phần tử `:visible`).
