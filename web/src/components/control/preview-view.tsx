import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { Badge, DataList, Money } from "@/components/ui";
import type { Preview, Source } from "@/lib/api/control";
import { formatNumber } from "@/lib/format";

const CHANNEL_LABELS: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  threads: "Threads",
  tiktok: "TikTok",
  zalo: "Zalo",
  zalo_oa: "Zalo OA",
  messenger: "Messenger",
  web: "Website",
  email: "Email",
};

const KNOWN = new Set(["kind", "text", "channel", "image_url", "images", "fields", "list", "lines", "total_vnd", "href"]);

/** Tên khoá lạ → chữ đọc được: `price_vnd` → «Price». Module nên dùng `fields` để có nhãn tiếng Việt. */
function humanize(key: string): string {
  const s = key.replace(/_vnd$/, "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Value({ value, format, keyName }: { value: unknown; format?: string; keyName?: string }) {
  if (value === null || value === undefined || value === "") return <span className="text-ink-3">—</span>;
  if (typeof value === "number") {
    return format === "vnd" || keyName?.endsWith("_vnd") ? <Money value={value} /> : <>{formatNumber(value)}</>;
  }
  if (typeof value === "boolean") return <>{value ? "Có" : "Không"}</>;
  if (typeof value === "string") return <>{value}</>;
  if (Array.isArray(value) && value.every((v) => typeof v === "string" || typeof v === "number")) return <>{value.join(", ")}</>;
  return <code className="text-[13px] break-all">{JSON.stringify(value)}</code>;
}

/** Xem trước một việc chờ duyệt theo `preview` (quy ước ở `lib/api/control.ts`). */
export function PreviewView({ preview }: { preview: Preview }) {
  const extra = Object.entries(preview).filter(([k, v]) => !KNOWN.has(k) && v !== null && v !== undefined);
  const images = [...(preview.image_url ? [preview.image_url] : []), ...(preview.images ?? [])];
  const empty = !preview.text && !preview.fields?.length && !preview.list?.length && !preview.lines?.length && !images.length && !extra.length;
  if (empty) return <p className="text-[15px] text-ink-2">Việc này không có phần xem trước.</p>;
  return (
    <div className="flex flex-col gap-3">
      {preview.channel ? (
        <div>
          <Badge tone="outline">{CHANNEL_LABELS[preview.channel] ?? preview.channel}</Badge>
        </div>
      ) : null}
      {preview.text ? (
        <div className="rounded-md border border-line bg-paper p-3 text-[15px] leading-relaxed whitespace-pre-line [overflow-wrap:anywhere]">
          {preview.text}
        </div>
      ) : null}
      {images.length ? (
        <div className="grid grid-cols-3 gap-2">
          {images.slice(0, 6).map((src) => (
            // eslint-disable-next-line @next/next/no-img-element -- ảnh xem trước từ nhiều nguồn, không qua next/image
            <img key={src} src={src} alt="" className="aspect-square w-full rounded-md bg-soft object-cover" />
          ))}
        </div>
      ) : null}
      {preview.list?.length ? (
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[15px]">
          {preview.list.map((li, i) => (
            <li key={i}>{li}</li>
          ))}
        </ul>
      ) : null}
      {preview.fields?.length ? (
        <DataList items={preview.fields.map((f) => ({ label: f.label, value: <Value value={f.value} format={f.format} /> }))} />
      ) : null}
      {preview.lines?.length ? (
        <DataList
          items={[
            ...preview.lines.map((ln) => ({
              label: (
                <span>
                  {ln.name}
                  {ln.quantity !== 1 ? <span className="text-ink-3"> × {ln.quantity}</span> : null}
                </span>
              ),
              value: <Money value={ln.quantity * ln.unit_price_vnd} />,
            })),
            ...(preview.total_vnd !== undefined ? [{ label: "Tổng", value: <Money value={preview.total_vnd} />, strong: true }] : []),
          ]}
        />
      ) : null}
      {extra.length ? (
        <DataList items={extra.map(([k, v]) => ({ label: humanize(k), value: <Value value={v} keyName={k} /> }))} />
      ) : null}
      {preview.href ? (
        <Link href={preview.href} className="inline-flex items-center gap-1 text-[15px] font-semibold text-accent">
          Mở trang chi tiết →
        </Link>
      ) : null}
    </div>
  );
}

/** Căn cứ AI nêu: lý do + nguồn dẫn. */
export function Rationale({ rationale, sources }: { rationale: string | null; sources: Source[] }) {
  if (!rationale && !sources.length) return null;
  return (
    <div className="flex flex-col gap-2 rounded-md bg-soft p-3 text-[14px]">
      <p className="font-semibold">Căn cứ</p>
      {rationale ? <p className="text-ink-2">{rationale}</p> : null}
      {sources.length ? (
        <ul className="flex flex-col gap-1">
          {sources.map((s, i) =>
            s.url ? (
              <li key={i}>
                <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent [overflow-wrap:anywhere]">
                  <ExternalLink className="size-3.5 shrink-0" aria-hidden />
                  {s.title || s.url}
                </a>
              </li>
            ) : null,
          )}
        </ul>
      ) : null}
    </div>
  );
}
