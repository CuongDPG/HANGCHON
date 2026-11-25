import { Check, ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { Badge, DataList, DateTime, Money } from "@/components/ui";
import { cn } from "@/lib/cn";
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

/** Nhãn tiếng Việt cho các khoá `preview` các module gửi lên (và khoá con trong đối tượng/mảng đối tượng). */
const LABELS: Record<string, string> = {
  address: "Địa chỉ",
  after: "Sau khi sửa",
  before: "Trước khi sửa",
  body: "Nội dung",
  candidate: "Món đang xét",
  channels: "Kênh",
  checks: "Kiểm tra",
  closes_at: "Đóng lúc",
  code: "Mã",
  contact: "Liên hệ",
  count: "Số lượng",
  currency: "Tiền tệ",
  customer: "Khách",
  customer_message: "Lời nhắn cho khách",
  description: "Mô tả",
  display_name: "Tên hiển thị",
  dropped_faq: "Câu hỏi đáp bị bỏ",
  dropped_specs: "Thông số bị bỏ",
  error: "Lỗi",
  expected_arrival_date: "Dự kiến hàng về",
  faq_count: "Số câu hỏi đáp",
  flags: "Đánh dấu",
  hashtags: "Hashtag",
  high: "Cao nhất",
  hint: "Gợi ý",
  idea: "Ý tưởng",
  intent: "Khách muốn",
  intent_label: "Khách muốn",
  items: "Món",
  label: "Nhãn",
  landed_cost_vnd: "Giá vốn về tay",
  link_url: "Đường dẫn",
  low: "Thấp nhất",
  margin_pct: "Biên lãi (%)",
  market: "Giá trên thị trường",
  median: "Giá giữa",
  message: "Tin nhắn của khách",
  minutes: "Phút",
  missing: "Còn thiếu",
  missing_info: "Còn thiếu",
  music: "Nhạc nền",
  name: "Tên",
  not_satisfied: "Điều chưa ưng",
  note_count: "Số ghi chú",
  notes: "Ghi chú",
  off_topic: "Lạc đề",
  offensive: "Xúc phạm",
  opens_at: "Mở lúc",
  options: "Phương án trả lời",
  order_code: "Mã đơn",
  outline: "Dàn ý",
  overclaims: "Câu nói quá",
  pass_score: "Điểm đạt",
  payment_method: "Cách trả tiền",
  personal_info: "Có thông tin cá nhân",
  phone: "Số điện thoại",
  photos: "Ảnh",
  price_vnd: "Giá",
  product: "Món",
  pronouns: "Xưng hô",
  proposed_drop_price_vnd: "Giá mua chung đề xuất",
  proposed_price_vnd: "Giá bán đề xuất",
  quantity: "Số lượng",
  question: "Câu hỏi",
  quote: "Trích đánh giá",
  rating: "Số sao",
  reason: "Lý do",
  reason_label: "Lý do",
  reason_selected: "Lý do chọn",
  recent_questions: "Câu hỏi gần đây",
  recipient: "Người nhận",
  recipient_count: "Số người nhận",
  recipient_name: "Người nhận",
  recommend: "AI đề xuất",
  refundable_vnd: "Số tiền có thể hoàn",
  rendered: "Đã dựng video",
  reply: "Câu trả lời",
  scheduled_at: "Giờ đăng",
  score: "Điểm",
  script: "Kịch bản",
  segment: "Phần",
  segments: "Các đoạn",
  caption: "Chú thích ảnh",
  image_index: "Ảnh số",
  matched: "Khớp món trên kệ",
  unit_price: "Đơn giá",
  unit_price_vnd: "Đơn giá",
  refund_amount: "Số tiền hoàn",
  refund_vnd: "Số tiền hoàn",
  refund_amount_vnd: "Số tiền hoàn",
  amount_vnd: "Số tiền",
  short_description: "Mô tả ngắn",
  slot_at: "Khung giờ",
  slots: "Số suất",
  spam: "Tin rác",
  style_summary: "Giọng văn",
  subtitle: "Dòng phụ",
  subtotal_amount: "Tiền hàng",
  summary: "Tóm tắt",
  supplier: "Nhà cung cấp",
  title: "Tiêu đề",
  unit_price_amount: "Đơn giá",
};

/** Nhãn riêng theo loại việc (`preview.kind`) khi cùng khoá mang nghĩa khác. */
const KIND_LABELS: Record<string, Record<string, string>> = {
  sample: { message: "Lời nhắn gửi nhà cung cấp" },
  batch: { message: "Lời nhắn gửi nhà cung cấp" },
  restock: { message: "Lời nhắn gửi nhà cung cấp" },
};

/** Giá trị mã hoá → chữ (các giá trị enum hay gặp trong xem trước). */
const VALUE_LABELS: Record<string, string> = {
  bank_transfer: "Chuyển khoản",
  cod: "Trả khi nhận hàng",
  defect: "Hàng lỗi",
  wrong_item: "Giao sai món",
  damaged: "Vỡ khi giao",
  not_as_described: "Khác mô tả",
  change_mind: "Đổi ý",
  refund_only: "Chỉ hoàn tiền",
  replace: "Gửi món thay",
  ask_product: "Hỏi về món",
  publish: "Hiện lên trang",
  hide: "Ẩn đi",
  review: "Để chị xem",
};

/** Khoá nội bộ không cho chị xem (mã định danh, cờ kỹ thuật, bản trùng với phần khác của hộp). */
function hidden(key: string, preview: Record<string, unknown>, omit: Set<string>): boolean {
  if (omit.has(key) || KNOWN.has(key)) return true;
  if (key === "id" || key.endsWith("_id") || key.endsWith("_key") || key === "ai_generated" || key === "tiktok_draft" || key === "overridden") return true;
  if (key === "channel_label" && preview.channel) return true;
  if (key === "reason" && preview.reason_label) return true;
  if (key === "intent" && preview.intent_label) return true;
  return false;
}

/** Tên khoá chưa có trong `LABELS` → chữ đọc được (dự phòng; nên bổ sung nhãn khi gặp). */
function labelOf(key: string, kind?: unknown): string {
  const byKind = typeof kind === "string" ? KIND_LABELS[kind]?.[key] : undefined;
  if (byKind) return byKind;
  if (LABELS[key]) return LABELS[key];
  const s = key.replace(/_(vnd|pct|label)$/, "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}.*)?$/;

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function Value({ value, format, keyName }: { value: unknown; format?: string; keyName?: string }) {
  if (isEmpty(value)) return <span className="text-ink-3">—</span>;
  if (typeof value === "number") {
    if (format === "vnd" || keyName?.endsWith("_vnd")) return <Money value={value} />;
    return <>{formatNumber(value)}{keyName?.endsWith("_pct") ? "%" : ""}</>;
  }
  if (typeof value === "boolean") return <>{value ? "Có" : "Không"}</>;
  if (typeof value === "string") {
    if (ISO_DATE.test(value)) return <DateTime value={value} format={value.length > 10 ? "dateTime" : "date"} />;
    if (/^https?:\/\//.test(value))
      return (
        <a href={value} target="_blank" rel="noreferrer" className="text-accent [overflow-wrap:anywhere]">
          {value}
        </a>
      );
    return <span className="whitespace-pre-line">{VALUE_LABELS[value] ?? value}</span>;
  }
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v === "string" || typeof v === "number")) {
      const strs = value.map((v) => (typeof v === "string" ? (VALUE_LABELS[v] ?? v) : formatNumber(v)));
      return strs.some((v) => v.length > 40) ? (
        <ul className="flex list-disc flex-col gap-1 pl-5">
          {strs.map((v, i) => (
            <li key={i}>{v}</li>
          ))}
        </ul>
      ) : (
        <>{strs.join(", ")}</>
      );
    }
    return (
      <div className="flex flex-col gap-2">
        {value.map((v, i) => (isRecord(v) ? <ObjectCard key={i} obj={v} /> : <Value key={i} value={v} />))}
      </div>
    );
  }
  if (isRecord(value)) return <KeyValues obj={value} nested />;
  return <>{String(value)}</>;
}

/** Một phần tử mảng đối tượng (phương án, mục kiểm tra, dòng dàn ý…): tiêu đề + nội dung + các ý phụ. */
function ObjectCard({ obj }: { obj: Record<string, unknown> }) {
  if (typeof obj.ok === "boolean" && typeof obj.label === "string") {
    return (
      <p className="flex items-start gap-2">
        {obj.ok ? <Check className="mt-0.5 size-4 shrink-0 text-success" aria-label="Đạt" /> : <X className="mt-0.5 size-4 shrink-0 text-seal" aria-label="Chưa đạt" />}
        <span>{obj.label}</span>
      </p>
    );
  }
  const headKey = ["label", "title", "name"].find((k) => typeof obj[k] === "string");
  const bodyKey = ["reply", "description", "notes", "text", "body"].find((k) => typeof obj[k] === "string");
  const rest = Object.fromEntries(Object.entries(obj).filter(([k]) => k !== headKey && k !== bodyKey && k !== "kind"));
  return (
    <div className="rounded-md border border-line bg-paper p-3">
      {headKey ? <p className="font-semibold">{String(obj[headKey])}</p> : null}
      {bodyKey ? <p className="mt-1 whitespace-pre-line text-ink-2">{String(obj[bodyKey])}</p> : null}
      {Object.keys(rest).length ? <KeyValues obj={rest} nested className="mt-1" /> : null}
    </div>
  );
}

/** Danh sách nhãn — giá trị, nhãn bên trái, giá trị canh trái để đọc được câu dài trên một dòng. */
function KeyValues({
  obj,
  preview,
  omit = new Set(),
  nested = false,
  className,
}: {
  obj: Record<string, unknown>;
  preview?: Record<string, unknown>;
  omit?: Set<string>;
  nested?: boolean;
  className?: string;
}) {
  const entries = Object.entries(obj).filter(([k, v]) => !isEmpty(v) && !hidden(k, preview ?? obj, omit) && !(nested && k === "kind"));
  if (!entries.length) return null;
  return (
    <dl
      className={cn(
        "grid grid-cols-1 gap-x-4 [overflow-wrap:anywhere]",
        nested ? "gap-y-1 text-[14px] sm:grid-cols-[minmax(6rem,auto)_1fr]" : "gap-y-2.5 text-[15px] sm:grid-cols-[10rem_1fr]",
        className,
      )}
    >
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-2">{labelOf(k, (preview ?? obj).kind)}</dt>
          <dd className="min-w-0 max-sm:mb-1">
            <Value value={v} keyName={k} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Xem trước một việc chờ duyệt theo `preview` (quy ước ở `lib/api/control.ts`). */
export function PreviewView({ preview, omit = [] }: { preview: Preview; /** Khoá đã hiện ở chỗ khác của hộp (vd. `summary` là mô tả hộp). */ omit?: string[] }) {
  const omitSet = new Set(omit);
  const extra = Object.entries(preview).filter(([k, v]) => !isEmpty(v) && !hidden(k, preview, omitSet));
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
                  {ln.name ?? ln.description}
                  {ln.quantity !== 1 ? <span className="text-ink-3"> × {ln.quantity}</span> : null}
                </span>
              ),
              // dòng đơn đặt nhà cung cấp tính theo ngoại tệ (`unit_price_amount` + `currency` của preview)
              value:
                typeof ln.unit_price_vnd === "number" ? (
                  <Money value={ln.quantity * ln.unit_price_vnd} />
                ) : (
                  <>
                    {formatNumber(ln.quantity * (ln.unit_price_amount ?? 0))} {typeof preview.currency === "string" ? preview.currency : ""}
                  </>
                ),
            })),
            ...(preview.total_vnd !== undefined ? [{ label: "Tổng", value: <Money value={preview.total_vnd} />, strong: true }] : []),
          ]}
        />
      ) : null}
      {extra.length ? <KeyValues obj={preview} preview={preview} omit={omitSet} /> : null}
      {preview.href && !omitSet.has("href") ? (
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
