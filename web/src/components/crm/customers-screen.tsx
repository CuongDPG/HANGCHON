"use client";

import { Search, UsersRound } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Badge, Button, CardLink, Chip, EmptyState, Money, PageHeader, SkeletonList, Toolbar, ToolbarSearch } from "@/components/ui";
import { useCustomers, type CustomerItem, type CustomerSegment } from "@/lib/api/crm";
import { CHANNEL_LABEL } from "@/lib/api/inbox";
import { KHACH_SECTIONS } from "@/lib/desk-sections";
import { useUrlParam } from "@/lib/use-url-param";

const SEGMENTS: { value: CustomerSegment; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "regular", label: "Khách quen" },
  { value: "new", label: "Chưa mua" },
  { value: "optout", label: "Từ chối nhận tin" },
];

/** Sổ khách (h4): mỗi khách đã mua gì, hỏi gì, quan tâm gì. Tìm không dấu theo tên, số điện thoại, ghi chú, nhãn. */
export function CustomersScreen() {
  const [segment, setSegment] = useUrlParam<CustomerSegment>("nhom", "all", ["all", "regular", "new", "optout"]);
  const [q, setQ] = useState("");
  const query = useDeferredValue(q.trim());
  const { data, isPending, error, refetch } = useCustomers({ q: query, segment });

  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={KHACH_SECTIONS} active="book" />
      <Toolbar
        end={<ToolbarSearch aria-label="Tìm khách" placeholder="Tên, số điện thoại, ghi chú, nhãn…" value={q} onChange={(e) => setQ(e.target.value)} />}
      >
        {SEGMENTS.map((s) => (
          <Chip key={s.value} selected={segment === s.value} count={segment === s.value ? data?.total : undefined} onClick={() => setSegment(s.value)}>
            {s.label}
          </Chip>
        ))}
      </Toolbar>
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được sổ khách"
          description={error.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={query ? <Search /> : <UsersRound />}
          title={query ? "Không thấy khách nào" : "Chưa có khách trong nhóm này"}
          description={query ? "Thử tìm không dấu hoặc bằng vài số cuối điện thoại." : "Khách có đơn hoặc nhắn tin sẽ được ghi vào sổ."}
        />
      ) : (
        <ul className="flex flex-col gap-2.5">
          {data.items.map((c) => (
            <li key={c.id}>
              <CustomerRow c={c} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CustomerRow({ c }: { c: CustomerItem }) {
  return (
    <CardLink href={`/desk/khach/so-khach/${c.id}`} className="flex flex-col gap-1.5">
      <span className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block truncate text-[15px] font-semibold">{c.name || c.phone || "Khách"}</span>
          <span className="block truncate text-[13px] text-ink-2">
            {[c.phone, ...c.channels.map((ch) => CHANNEL_LABEL[ch] ?? ch)].filter(Boolean).join(" · ")}
          </span>
        </span>
        <span className="shrink-0 text-right text-[13px] text-ink-2">
          {c.order_count ? (
            <>
              <span className="block font-semibold text-ink">
                <Money value={c.total_spent_vnd} />
              </span>
              {c.order_count} đơn
            </>
          ) : (
            "Chưa mua"
          )}
        </span>
      </span>
      {c.summary ? <span className="line-clamp-2 text-[14px] text-ink-2 [text-wrap:pretty]">{c.summary}</span> : null}
      {c.is_regular || c.opted_out || c.tags.length ? (
        <span className="flex flex-wrap gap-1.5">
          {c.is_regular ? <Badge tone="accent">Khách quen</Badge> : null}
          {c.opted_out ? <Badge tone="danger">Từ chối nhận tin</Badge> : null}
          {c.tags
            .filter((t) => t !== "khach-quen" && t !== "tu-choi-nhan-tin")
            .slice(0, 3)
            .map((t) => (
              <Badge key={t} tone="outline">
                {t}
              </Badge>
            ))}
        </span>
      ) : null}
    </CardLink>
  );
}
