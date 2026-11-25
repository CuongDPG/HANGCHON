"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card, SectionLabel } from "@/components/ui/card";
import { DataList, StatTile } from "@/components/ui/data-display";
import { DateTime } from "@/components/ui/date-time";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { Money } from "@/components/ui/money";
import { useSalesDossier, type ContentState, type SalesDossier } from "@/lib/api/catalog";
import { cn } from "@/lib/cn";
import { formatNumber, formatVndCompact } from "@/lib/format";

const STATE_TONE: Record<ContentState, BadgeTone> = { none: "outline", drafting: "neutral", pending: "warning", approved: "success" };
const SALE_MODE: Record<string, string> = { drop: "Bán theo đợt", in_stock: "Giữ sẵn", both: "Theo đợt + giữ sẵn" };

/**
 * Tab «Hồ sơ bán»: đi xuôi đường bán của một món — nội dung từng kênh đã sẵn chưa → đã lên kênh nào → khách phản hồi
 * và đặt ra sao. Chỉ hiện số hệ thống thật sự ghi; số từ kênh chưa nối thật (driver mock) gắn nhãn «giả lập».
 */
export function SalesDossierView({ productId, slug }: { productId: string; slug: string }) {
  const { data: d, isPending, error } = useSalesDossier(productId);
  if (isPending) return <SkeletonList rows={5} />;
  if (error || !d) return <EmptyState tone="error" title="Chưa tải được hồ sơ bán" description={error?.message} />;
  const o = d.customers.orders;

  return (
    <div className="flex flex-col gap-6">
      <ol className="grid gap-2 md:grid-cols-3" aria-label="Đường bán">
        <Stage n={1} title="Nội dung" value={`${d.content.ready}/${d.content.total}`} hint="kênh đã duyệt nội dung" href="#noi-dung" />
        <Stage
          n={2}
          title="Lên kênh"
          value={String(d.live.channels_live.length)}
          hint={d.live.channels_live.length ? d.live.channels_live.join(" · ") : "chưa lên kênh nào"}
          href="#len-kenh"
        />
        <Stage
          n={3}
          title="Khách hàng"
          value={`${formatNumber(o.count)} đơn`}
          hint={o.count ? `${formatNumber(o.units)} cái · đã thu ${formatVndCompact(o.revenue_vnd)}` : "chưa có đơn"}
          href="#khach-hang"
          last
        />
      </ol>

      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        <ContentBlock d={d} productId={productId} />
        <LiveBlock d={d} slug={slug} />
      </div>

      <CustomersBlock d={d} />
    </div>
  );
}

function Stage({ n, title, value, hint, href, last }: { n: number; title: string; value: string; hint: string; href: string; last?: boolean }) {
  return (
    <li className="relative min-w-0">
      <a href={href} className="flex h-full items-center gap-3 rounded-md border border-line bg-surface p-3 transition-colors hover:border-ink-3">
        <span aria-hidden className="inline-grid size-7 shrink-0 place-items-center rounded-sm bg-accent-wash font-display text-[14px] font-bold text-accent">
          {n}
        </span>
        <span className="min-w-0">
          <span className="block text-[13px] font-semibold tracking-[0.04em] text-ink-2 uppercase">{title}</span>
          <span className="block font-display text-[22px] leading-tight font-extrabold tabular-nums">{value}</span>
          <span className="block truncate text-[13px] text-ink-2">{hint}</span>
        </span>
      </a>
      {!last ? <ArrowRight aria-hidden className="absolute top-1/2 -right-2.5 z-10 hidden size-4 -translate-y-1/2 rounded-full bg-paper text-ink-3 md:block" /> : null}
    </li>
  );
}

function Block({ id, title, aside, children, className }: { id: string; title: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section id={id} className={cn("flex scroll-mt-24 flex-col gap-3", className)} aria-label={title}>
      <SectionLabel aside={aside} className="min-h-7">{title}</SectionLabel>
      {children}
    </section>
  );
}

function SmallLink({ href, children, external }: { href: string; children: ReactNode; external?: boolean }) {
  const cls = "text-[14px] font-semibold whitespace-nowrap text-accent hover:underline";
  return external ? (
    <a href={href} target="_blank" rel="noreferrer" className={cls}>
      {children}
    </a>
  ) : (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

function Simulated({ children = "Số liệu giả lập" }: { children?: ReactNode }) {
  return <Badge tone="warning">{children}</Badge>;
}

/* ---------- a. Nội dung ---------- */

function ContentBlock({ d, productId }: { d: SalesDossier; productId: string }) {
  const studio = `/desk/noi-dung/san-pham/${productId}`;
  const rows: { key: string; label: string; state: ContentState; state_label: string; at: string | null }[] = [
    { key: "website", label: "Website", state: d.content.website.state, state_label: d.content.website.state_label, at: d.content.website.updated_at },
    ...d.content.channels.map((c) => ({ key: c.channel, label: c.label, state: c.state, state_label: c.state_label, at: c.updated_at })),
  ];
  return (
    <Block id="noi-dung" title="1 · Nội dung" aside={<SmallLink href={studio}>Xưởng nội dung →</SmallLink>}>
      <Card className="border border-line" flush>
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <li key={r.key}>
              <Link href={`${studio}?kenh=${r.key}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-soft-2/60">
                <span className="min-w-0 flex-1 text-[15px] font-semibold">{r.label}</span>
                {r.at && r.state !== "none" ? (
                  <span className="hidden text-[13px] text-ink-3 sm:inline">
                    <DateTime value={r.at} format="relative" />
                  </span>
                ) : null}
                <Badge tone={STATE_TONE[r.state]}>{r.key === "website" && r.state === "approved" ? "Đã duyệt trang" : r.state_label}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-[13px] text-ink-2">
        {d.content.ready}/{d.content.total} kênh đã duyệt. Bấm một kênh để mở đúng tab trong xưởng nội dung.
      </p>
    </Block>
  );
}

/* ---------- b. Lên kênh ---------- */

function LiveBlock({ d, slug }: { d: SalesDossier; slug: string }) {
  const w = d.live.website;
  const anySimPost = d.live.posts.some((p) => p.simulated);
  return (
    <Block id="len-kenh" title="2 · Lên kênh">
      <Card className="flex flex-col gap-3 border border-line">
        <Row
          label="Website"
          meta={w.published && w.published_at ? <>đăng <DateTime value={w.published_at} /></> : w.status === "paused" ? "đang tạm ẩn" : "chưa đăng"}
          right={w.published ? <SmallLink href={`/san-pham/${slug}`} external>Xem trang ↗</SmallLink> : <Badge tone="outline">Chưa lên web</Badge>}
        />
        {d.live.posts.length ? (
          d.live.posts.map((p) => (
            <Row
              key={p.id}
              label={p.label}
              meta={
                p.published_at ? (
                  <>đăng <DateTime value={p.published_at} format="dateTime" /></>
                ) : (
                  <>hẹn <DateTime value={p.scheduled_at} format="dateTime" /></>
                )
              }
              right={
                <span className="flex items-center gap-2">
                  {p.simulated ? <Simulated>Giả lập</Simulated> : null}
                  {p.url && !p.simulated ? <SmallLink href={p.url} external>Mở bài ↗</SmallLink> : null}
                  <Badge tone={p.status === "published" ? "success" : p.status === "failed" ? "danger" : "accent"}>{p.status_label}</Badge>
                </span>
              }
            />
          ))
        ) : (
          <p className="text-[14px] text-ink-2">Chưa có bài mạng xã hội nào lên lịch.</p>
        )}
        {d.live.drops.map((dr) => (
          <Row
            key={dr.id}
            label={<Link href={`/desk/san-pham/dot/${dr.id}`} className="hover:underline">Đợt {dr.code}</Link>}
            meta={
              <>
                {dr.title} · <Money value={dr.price_vnd} />
                {dr.slots_total ? ` · ${dr.slots_reserved}/${dr.slots_total} suất` : ""}
              </>
            }
            right={<Badge tone={dr.status === "open" ? "success" : "neutral"}>{dr.status_label}</Badge>}
          />
        ))}
        {d.live.marketplaces.length ? (
          d.live.marketplaces.map((m) => (
            <Row
              key={m.marketplace}
              label={m.label}
              meta={<>{m.price_vnd ? <Money value={m.price_vnd} /> : null}{m.synced_stock !== null ? ` · tồn đẩy lên ${m.synced_stock}` : ""}</>}
              right={
                <span className="flex items-center gap-2">
                  {d.live.marketplaces_simulated ? <Simulated>Sàn giả lập</Simulated> : null}
                  <Badge tone={m.status === "active" ? "success" : m.status === "error" ? "danger" : "neutral"}>{m.status_label}</Badge>
                </span>
              }
            />
          ))
        ) : (
          <Row
            label="Shopee · TikTok Shop"
            meta={d.live.marketplaces_simulated ? "chưa nối sàn thật" : "chưa đưa món này lên sàn"}
            right={<SmallLink href="/desk/don-hang/van-hanh?tab=san">Đồng bộ sàn →</SmallLink>}
          />
        )}
      </Card>
      {anySimPost ? (
        <p className="text-[13px] text-ink-2">Kênh mạng xã hội đang chạy bản giả lập (chưa nối tài khoản thật ở Cài đặt → Tích hợp), nên bài «đã đăng» chưa thật sự lên kênh.</p>
      ) : null}
    </Block>
  );
}

function Row({ label, meta, right }: { label: ReactNode; meta?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <div className="min-w-0">
        <p className="text-[15px] font-semibold">{label}</p>
        {meta ? <p className="text-[13px] text-ink-2">{meta}</p> : null}
      </div>
      {right}
    </div>
  );
}

/* ---------- c. Khách hàng ---------- */

function CustomersBlock({ d }: { d: SalesDossier }) {
  const c = d.customers;
  const o = c.orders;
  const reminders = d.live.drops.reduce((n, x) => n + x.reminders, 0);
  return (
    <Block id="khach-hang" title="3 · Khách hàng">
      <div className="grid gap-4 lg:grid-cols-3 lg:items-start">
        <Card className="flex flex-col gap-3 border border-line">
          <h3 className="text-[15px] font-semibold">Đơn hàng</h3>
          <div className="grid grid-cols-3 gap-2">
            <StatTile value={formatNumber(o.count)} label="đơn" />
            <StatTile value={formatNumber(o.units)} label="cái" />
            <StatTile value={formatVndCompact(o.revenue_vnd)} label="đã thu" />
          </div>
          {o.count || o.drafts || o.cancelled ? (
            <>
              <DataList
                items={[
                  ...(o.unpaid_vnd ? [{ label: "Chờ thu", value: <Money value={o.unpaid_vnd} /> }] : []),
                  { label: "Khách đã mua", value: `${o.customers}${o.repeat_buyers ? ` · ${o.repeat_buyers} người mua lại` : ""}` },
                  ...(o.by_channel.length ? [{ label: "Theo kênh", value: o.by_channel.map((x) => `${x.label} ${x.count}`).join(" · ") }] : []),
                ]}
              />
              <ul className="flex flex-wrap gap-1.5" aria-label="Theo trạng thái">
                {o.by_status.map((s) => (
                  <li key={s.status ?? s.label} className="rounded-md border border-line px-2 py-0.5 text-[13px]">
                    {s.label} <span className="text-ink-3 tabular-nums">· {s.count}</span>
                  </li>
                ))}
              </ul>
              <ul className="flex flex-col divide-y divide-line">
                {o.recent.map((r) => (
                  <li key={r.id}>
                    <Link href={`/desk/don-hang/${r.id}`} className="flex items-center justify-between gap-2 py-1.5 text-[14px] hover:underline">
                      <span className="min-w-0 truncate">
                        <span className="font-semibold">{r.code}</span> · {r.name} · {r.quantity} cái
                      </span>
                      <span className="shrink-0 text-ink-2">{r.status_label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-[14px] text-ink-2">Chưa có đơn nào có món này.</p>
          )}
        </Card>

        <Card className="flex flex-col gap-3 border border-line">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[15px] font-semibold">Khách quan tâm</h3>
            {c.posts.simulated ? <Simulated /> : null}
          </div>
          {c.posts.measured_posts ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <StatTile value={formatNumber(c.posts.reach)} label="người thấy" />
                <StatTile value={formatNumber(c.posts.clicks)} label="bấm link" />
                <StatTile value={formatNumber(c.posts.interactions)} label="tương tác" />
              </div>
              <p className="text-[13px] text-ink-2">
                Từ {c.posts.measured_posts} bài đã đo
                {c.posts.last_captured_at ? <>, lần đo gần nhất <DateTime value={c.posts.last_captured_at} format="relative" /></> : null}.
                {c.posts.orders_from_posts ? ` ${c.posts.orders_from_posts} đơn đặt qua link trong bài (thật, theo mã nguồn).` : ""}
                {c.posts.simulated ? " Lượt thấy, bấm, tương tác lấy từ kênh giả lập." : ""}
              </p>
            </>
          ) : (
            <p className="text-[14px] text-ink-2">Chưa đo số liệu bài nào{d.live.posts.length ? " (máy đo chạy mỗi giờ sau khi bài lên)" : ""}.</p>
          )}
          <DataList
            items={[
              {
                label: "Hộp thư hỏi về món",
                value: c.inbox.threads ? `${c.inbox.threads} hội thoại${c.inbox.needs_owner ? ` · ${c.inbox.needs_owner} chờ chị` : ""}` : "chưa có",
              },
              { label: "Hỏi trợ lý trên web", value: c.assistant.conversations ? `${c.assistant.conversations} lượt${c.assistant.handed_off ? ` · ${c.assistant.handed_off} chuyển chị` : ""}` : "chưa có" },
              ...(reminders ? [{ label: "Bấm «Nhắc mình» ở đợt", value: `${reminders} người` }] : []),
              ...(c.finds.length ? [{ label: "Từ «Nhờ tìm»", value: c.finds.map((f) => `${f.title} (${f.votes} người cần)`).join(" · ") }] : []),
              ...(c.reorder.scheduled || c.reorder.sent || c.reorder.converted
                ? [{ label: "Nhắc mua lại", value: `${c.reorder.scheduled} chờ nhắc · ${c.reorder.sent} đã nhắc · ${c.reorder.converted} mua lại` }]
                : []),
            ]}
          />
          {c.inbox.recent.length ? (
            <ul className="flex flex-col gap-1.5">
              {c.inbox.recent.map((t) => (
                <li key={t.id}>
                  <Link href={`/desk/khach/hoi-thoai/${t.id}`} className="block rounded-md bg-soft px-3 py-2 text-[14px] hover:bg-soft-2">
                    <span className="font-semibold">{t.name ?? "Khách"}</span> <span className="text-ink-3">· {t.channel_label}</span>
                    {t.snippet ? <span className="block truncate text-ink-2">{t.snippet}</span> : null}
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>

        <Card className="flex flex-col gap-3 border border-line">
          <h3 className="text-[15px] font-semibold">Tồn kho và đánh giá</h3>
          <DataList
            items={[
              { label: "Cách bán", value: SALE_MODE[c.stock.sale_mode] ?? c.stock.sale_mode },
              ...(c.stock.tracked
                ? [
                    { label: "Còn bán được", value: <span className={c.stock.low ? "font-semibold text-seal" : undefined}>{c.stock.available}{c.stock.low ? " · sắp hết" : ""}</span> },
                    { label: "Trong kho / đang giữ", value: `${c.stock.on_hand} / ${c.stock.reserved}` },
                  ]
                : [{ label: "Tồn giữ sẵn", value: "chưa nhập kho" }]),
              {
                label: "Đánh giá hiển thị",
                value: c.reviews.published ? `${c.reviews.rating_avg?.toLocaleString("vi-VN", { maximumFractionDigits: 1 }) ?? "–"}★ · ${c.reviews.published} lượt` : "chưa có",
              },
              ...(c.reviews.waiting_owner ? [{ label: "Đánh giá chờ chị duyệt", value: String(c.reviews.waiting_owner) }] : []),
              ...(c.reviews.requested ? [{ label: "Đã xin, chờ khách viết", value: String(c.reviews.requested) }] : []),
            ]}
          />
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {c.reviews.waiting_owner ? <SmallLink href="/desk/san-pham/danh-gia">Duyệt đánh giá →</SmallLink> : null}
            {c.stock.tracked ? <SmallLink href="/desk/don-hang/van-hanh?tab=ton">Kho →</SmallLink> : null}
          </div>
        </Card>
      </div>
    </Block>
  );
}
