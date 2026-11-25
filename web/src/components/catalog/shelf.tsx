import { HandHelping, Hourglass, Search, SearchX, Stamp } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { ChipRow } from "@/components/ui/chip";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { catalogApi, type Shelf } from "@/lib/api/catalog";
import { errorMessage } from "@/lib/api/client";
import { ChipLink } from "./chip-link";
import { ProductCard } from "./product-card";

function hrefFor(nhom: string | null, q: string | null) {
  const sp = new URLSearchParams();
  if (nhom) sp.set("nhom", nhom);
  if (q) sp.set("q", q);
  const s = sp.toString();
  return s ? `/?${s}` : "/";
}

/** Ô tìm hiểu câu nói thường ngày (không dấu cũng được). Gửi bằng GET để chạy cả khi chưa tải JavaScript. */
export function ShelfSearch({ q, nhom }: { q?: string | null; nhom?: string | null }) {
  return (
    <form action="/" method="get" role="search" className="flex gap-2">
      {nhom ? <input type="hidden" name="nhom" value={nhom} /> : null}
      <Input
        name="q"
        type="search"
        defaultValue={q ?? ""}
        placeholder="Bạn đang cần gì? vd. bình nước cho bé"
        aria-label="Tìm trên kệ"
        leading={<Search />}
        wrapperClassName="flex-1"
        enterKeyHint="search"
        autoComplete="off"
        maxLength={120}
      />
    </form>
  );
}

export function ShelfSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Đang tải kệ hàng">
      <Skeleton className="h-11 w-full" />
      <div className="flex gap-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-9 w-20" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-6 md:grid-cols-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex flex-col gap-2">
            <Skeleton className="aspect-square w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/3" />
          </div>
        ))}
      </div>
    </div>
  );
}

export async function ShelfResults({ q, nhom }: { q: string | null; nhom: string | null }) {
  let shelf: Shelf;
  try {
    shelf = await catalogApi.shelf({ q, nhom });
  } catch (err) {
    return (
      <div className="flex flex-col gap-4">
        <ShelfSearch q={q} nhom={nhom} />
        <EmptyState tone="error" title="Chưa tải được kệ hàng" description={errorMessage(err)} />
      </div>
    );
  }
  if (shelf.total === 0) {
    return (
      <EmptyState
        icon={<Stamp />}
        title="Kệ hàng đang được xếp"
        description="Những món đầu tiên còn đang trong thời gian dùng thử. Bạn đang cần món gì, cứ nhờ mình tìm giúp."
        action={
          <>
            <ButtonLink href="/nho-tim" icon={<HandHelping className="size-4" />}>
              Nhờ tìm
            </ButtonLink>
            <ButtonLink href="/dot" variant="secondary" icon={<Hourglass className="size-4" />}>
              Xem mua chung
            </ButtonLink>
          </>
        }
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <ShelfSearch q={q} nhom={nhom} />
      <nav aria-label="Lọc theo nhu cầu">
        <ChipRow>
          <ChipLink href={hrefFor(null, q)} selected={!nhom} count={shelf.total}>
            Tất cả
          </ChipLink>
          {shelf.chips.map((c) => (
            <ChipLink key={c.slug} href={hrefFor(c.slug, q)} selected={nhom === c.slug} count={c.count}>
              {c.name}
            </ChipLink>
          ))}
        </ChipRow>
      </nav>
      {q ? (
        <p className="text-[14px] text-ink-2" aria-live="polite">
          {shelf.items.length ? `${shelf.items.length} món khớp «${q}»` : null}
        </p>
      ) : null}
      {shelf.items.length === 0 ? (
        <EmptyState
          icon={<SearchX />}
          title={q ? `Kệ chưa có món nào khớp «${q}»` : "Nhóm này chưa có món nào"}
          description="Mình chỉ bày món đã tự mua và dùng thử. Bạn cần món này thì nhờ mình tìm — đủ người cùng cần, mình sẽ đi tìm và thử."
          action={
            <ButtonLink href={q ? `/nho-tim?tim=${encodeURIComponent(q)}` : "/nho-tim"} icon={<HandHelping className="size-4" />}>
              Nhờ tìm
            </ButtonLink>
          }
        />
      ) : (
        <ul className="grid grid-cols-2 gap-x-3 gap-y-6 md:grid-cols-3 md:gap-x-5 lg:grid-cols-4">
          {shelf.items.map((p, i) => (
            <li key={p.id} className="min-w-0">
              <ProductCard product={p} priority={i < 2} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
