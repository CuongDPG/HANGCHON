"use client";

import { Megaphone } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { CardLink } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { EmptyState, SkeletonList } from "@/components/ui/feedback";
import { ImageBox } from "@/components/ui/image-box";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
import { Toolbar, ToolbarSearch } from "@/components/ui/toolbar";
import { useContentBoard, type BoardChannelKey, type BoardRow, type BoardStage } from "@/lib/api/content";
import { CONTENT_SECTIONS } from "@/lib/desk-sections";
import { useUrlParam } from "@/lib/use-url-param";
import { BOARD_CHANNEL_LABEL, BOARD_CHANNELS, ChannelStrip, KpiLine, STAGE } from "./board-parts";
import { CONTENT_SETTINGS, localFile } from "./shared";

type Tab = BoardStage | "all";
const TABS: Tab[] = ["todo", "review", "scheduled", "published", "all"];
const CHANNEL_KEYS = ["", ...BOARD_CHANNELS] as const;

/** Xưởng (f1, f3, f7): bảng theo dõi nội dung theo món — mỗi món một dòng, trạng thái từng kênh và số liệu bài. */
export function ContentHome() {
  const [tab, setTab] = useUrlParam<Tab>("tab", "all", TABS);
  const [channel, setChannel] = useUrlParam<BoardChannelKey | "">("kenh", "", CHANNEL_KEYS);
  const [q, setQ] = useState("");
  const { data, isPending, error } = useContentBoard({ tab, q: q.trim() || undefined, channel: channel || null });
  const rows = data?.items ?? [];
  const counts = data?.counts;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={CONTENT_SECTIONS} active="studio" settings={CONTENT_SETTINGS} />
      <Tabs
        aria-label="Bước nội dung"
        value={tab}
        onChange={setTab}
        items={TABS.map((t) => ({ value: t, label: t === "all" ? "Tất cả" : STAGE[t].label, count: counts?.[t] }))}
      />
      <Toolbar end={<ToolbarSearch value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm món" aria-label="Tìm món" />}>
        <Chip selected={!channel} onClick={() => setChannel("")}>
          Mọi kênh
        </Chip>
        {BOARD_CHANNELS.map((c) => (
          <Chip key={c} selected={channel === c} onClick={() => setChannel(channel === c ? "" : c)}>
            {BOARD_CHANNEL_LABEL[c]}
          </Chip>
        ))}
      </Toolbar>
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được xưởng nội dung" description={error.message} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Megaphone />}
          title={counts?.all ? "Không có món nào ở bước này" : "Chưa có món nào được chọn"}
          description={
            counts?.all
              ? undefined
              : "Khi chị đóng dấu «Đã chọn» ở Bàn chọn, món về đây: AI viết trang website, chị đăng, rồi AI soạn bài cho Facebook, Instagram, Threads, TikTok và Zalo."
          }
        />
      ) : (
        <ul className="flex flex-col gap-2">
          <li
            aria-hidden
            className="hidden grid-cols-[3.5rem_minmax(0,1.2fr)_minmax(0,1.6fr)_minmax(0,1.1fr)_7.5rem] gap-x-3 px-3 text-[12.5px] font-semibold tracking-[0.06em] text-ink-3 uppercase md:grid"
          >
            <span />
            <span>Món</span>
            <span>Nội dung từng kênh</span>
            <span>Số liệu bài đã đăng</span>
            <span className="text-right">Bước</span>
          </li>
          {rows.map((r) => (
            <li key={`${r.kind}-${r.id}`}>
              <BoardItem row={r} channel={channel || null} />
            </li>
          ))}
          {data && data.total > rows.length ? (
            <li className="px-3 text-[13px] text-ink-3">
              Đang hiện {rows.length}/{data.total} món — tìm theo tên để thấy món khác.
            </li>
          ) : null}
        </ul>
      )}
    </div>
  );
}

function BoardItem({ row, channel }: { row: BoardRow; channel: BoardChannelKey | null }) {
  const base = `/desk/noi-dung/${row.kind === "drop" ? "dot" : "san-pham"}/${row.id}`;
  // đang lọc một kênh thì mở thẳng tab kênh đó trong Hồ sơ nội dung
  const href = channel && !(channel === "website" && row.kind === "drop") ? `${base}?kenh=${channel}` : base;
  const stage = STAGE[row.stage];
  return (
    <CardLink
      href={href}
      className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 p-3 md:grid-cols-[3.5rem_minmax(0,1.2fr)_minmax(0,1.6fr)_minmax(0,1.1fr)_7.5rem]"
    >
      <div className="row-span-3 w-14 md:row-span-1">
        {row.kind === "drop" ? (
          <div className="grid aspect-square place-items-center rounded-md bg-accent-wash font-display text-[13px] font-bold text-accent">ĐỢT</div>
        ) : (
          <ImageBox src={localFile(row.image_url)} alt="" ratio="1/1" placeholder="Ảnh" />
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate text-[15px] font-semibold">{row.name}</p>
        <p className="truncate text-[13px] text-ink-2">{row.subtitle ?? (row.kind === "drop" ? "Đợt mở bán" : "Sản phẩm")}</p>
      </div>
      <div className="justify-self-end md:order-last">
        <Badge tone={stage.tone}>{stage.label}</Badge>
      </div>
      <div className="col-span-2 col-start-2 min-w-0 md:col-span-1 md:col-start-auto">
        <ChannelStrip cells={row.channels} only={channel} />
      </div>
      <KpiLine kpi={row.kpi} className="col-span-2 col-start-2 md:col-span-1 md:col-start-auto" />
    </CardLink>
  );
}
