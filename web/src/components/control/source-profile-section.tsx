"use client";

import { FlaskConical, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Input, Segmented, Textarea, notifySuccess, useConfirm } from "@/components/ui";
import { errorMessage } from "@/lib/api/client";
import {
  useResetSourceProfile,
  useSaveSourceProfile,
  useTrySourceProfile,
  type SourceProfile,
  type SourceProfileFields,
  type SourceProfileTry,
} from "@/lib/api/control";

/**
 * «Cấu hình nâng cao» của một nguồn (gập sẵn): cách nhận ra link sản phẩm, link chuẩn, máy chủ ảnh, quy tắc đổi ảnh nhỏ
 * sang ảnh lớn, header khi tải, cách đọc trang, lời dặn AI. Ô nào chị đã sửa có nhãn «đã sửa» + nút về mặc định.
 * «Thử với một link» chạy trên bản đang sửa (chưa cần lưu), không gọi AI. Giải thích từng ô: docs/source-accounts.md.
 */

type Key = keyof SourceProfileFields;
type Kind = "lines" | "csv" | "rules" | "headers" | "text" | "long" | "number" | "via";

const FIELDS: { key: Key; label: string; kind: Kind; hint: string; placeholder?: string }[] = [
  { key: "domains", label: "Tên miền của sàn", kind: "lines", hint: "Mỗi dòng một tên miền (gồm cả tên miền con), vd amazon.co.jp." },
  {
    key: "url_patterns",
    label: "Mẫu link sản phẩm",
    kind: "lines",
    hint: "Mỗi dòng một biểu thức (regex) có nhóm (?P<id>…) để lấy mã món, vd /dp/(?P<id>[A-Z0-9]{10}).",
  },
  {
    key: "canonical_url",
    label: "Link chuẩn",
    kind: "text",
    hint: "Dựng lại link ngắn từ mã món, phải có {id}. Để trống = giữ link gốc, chỉ bỏ tham số.",
    placeholder: "https://www.amazon.co.jp/dp/{id}",
  },
  { key: "keep_params", label: "Tham số giữ lại", kind: "csv", hint: "Cách nhau bằng dấu phẩy. «*» = giữ mọi tham số trừ tham số theo dõi (utm_…, spm…). Trống = bỏ hết." },
  {
    key: "image_hosts",
    label: "Máy chủ ảnh",
    kind: "lines",
    hint: "Chỉ nhận ảnh ở đây; mỗi dòng một mẫu, vd *.alicdn.com hoặc m.media-amazon.com/images/I/*. Trống = mọi nơi.",
  },
  {
    key: "image_rewrites",
    label: "Đổi link ảnh sang ảnh lớn",
    kind: "rules",
    hint: "Mỗi dòng «tìm => thay bằng» (regex, áp lần lượt), vd \\._AC_[A-Z0-9_,]+_\\.jpg$ => .jpg",
  },
  { key: "fetch_headers", label: "Header khi tải ảnh / đọc trang", kind: "headers", hint: "Mỗi dòng «Tên: giá trị». Dùng được Referer, User-Agent, Accept-Language, Origin, Accept." },
  { key: "fetch_via", label: "Cách đọc trang chi tiết", kind: "via", hint: "«Không đọc trang» khi trang luôn bị chặn (captcha): khỏi tốn tiền AI." },
  {
    key: "page_image_patterns",
    label: "Mẫu ảnh trong trang",
    kind: "lines",
    hint: "Máy chủ tự đọc trang (không tốn AI) và lấy ảnh theo các regex này, nhóm (…) đầu tiên là link ảnh. Trống = không đọc.",
  },
  { key: "prompt_hints", label: "Dặn thêm AI", kind: "long", hint: "Vài dòng ngắn thêm vào lời dặn AI khi tìm / đọc trang sàn này." },
  { key: "max_images", label: "Số ảnh tối đa", kind: "number", hint: "Từ 1 đến 12 ảnh mỗi món." },
];

function kindOf(key: Key): Kind {
  return FIELDS.find((f) => f.key === key)!.kind;
}

function toText(key: Key, v: SourceProfileFields[Key]): string {
  const kind = kindOf(key);
  if (kind === "lines") return (v as string[]).join("\n");
  if (kind === "csv") return (v as string[]).join(", ");
  if (kind === "rules") return (v as SourceProfileFields["image_rewrites"]).map((r) => `${r.pattern} => ${r.replace}`).join("\n");
  if (kind === "headers") return Object.entries(v as Record<string, string>).map(([k, x]) => `${k}: ${x}`).join("\n");
  return String(v ?? "");
}

function fromText(key: Key, text: string): unknown {
  const kind = kindOf(key);
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (kind === "lines") return lines;
  if (kind === "csv") return text.split(",").map((x) => x.trim()).filter(Boolean);
  if (kind === "rules")
    return lines.map((l) => {
      const i = l.lastIndexOf("=>");
      return i < 0 ? { pattern: l, replace: "" } : { pattern: l.slice(0, i).trim(), replace: l.slice(i + 2).trim() };
    });
  if (kind === "headers")
    return Object.fromEntries(
      lines.map((l) => {
        const i = l.indexOf(":");
        return i < 0 ? [l, ""] : [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      }),
    );
  if (kind === "number") return Number(text.trim());
  return text.trim();
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function initial(p: SourceProfile): Record<Key, string> {
  return Object.fromEntries(FIELDS.map((f) => [f.key, toText(f.key, p.effective[f.key])])) as Record<Key, string>;
}

export function SourceProfileSection({ profile }: { profile: SourceProfile }) {
  const [text, setText] = useState<Record<Key, string>>(() => initial(profile));
  const [seen, setSeen] = useState(profile.effective);
  const save = useSaveSourceProfile();
  const reset = useResetSourceProfile();
  const confirm = useConfirm();
  if (!same(seen, profile.effective)) {
    // dữ liệu máy chủ đổi (vừa lưu / khôi phục) → nạp lại ô
    setSeen(profile.effective);
    setText(initial(profile));
  }
  const changed = FIELDS.filter((f) => !same(fromText(f.key, text[f.key]), profile.effective[f.key])).map((f) => f.key);
  const draft = Object.fromEntries(changed.map((k) => [k, fromText(k, text[k])]));
  const n = profile.overridden.length;

  function onSave() {
    // lỗi kiểm (400) hiện ở toast chung của mutation; giữ nguyên ô để chị sửa tiếp
    save.mutate({ platform: profile.platform, fields: draft }, { onSuccess: () => notifySuccess(`Đã lưu cấu hình nâng cao ${profile.label}`) });
  }

  async function onReset() {
    const ok = await confirm({
      title: `Khôi phục mặc định cho ${profile.label}?`,
      message: "Mọi ô chị đã sửa trong cấu hình nâng cao của nguồn này trở về mặc định.",
      confirmLabel: "Khôi phục",
    });
    if (!ok) return;
    reset.mutate(profile.platform, { onSuccess: () => notifySuccess(`${profile.label}: đã về mặc định`) });
  }

  return (
    <details className="rounded-md border border-line p-3 text-[14px] [&[open]>summary]:mb-3">
      <summary className="cursor-pointer font-semibold">
        Cấu hình nâng cao{" "}
        {n ? (
          <Badge tone="warning" className="ml-1 align-middle">
            Đã sửa {n} ô
          </Badge>
        ) : (
          <span className="font-normal text-ink-2">(đang dùng mặc định)</span>
        )}
      </summary>
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-ink-2">
          Cách Hàng Chọn nhận ra link sản phẩm của {profile.label}, rút gọn link, lấy ảnh lớn và tải ảnh. Chỉ sửa khi chị biết ô đó dùng
          làm gì; sai thì bấm «Khôi phục mặc định».
        </p>
        {FIELDS.map((f) => {
          const overridden = profile.overridden.includes(f.key);
          const isDefault = same(fromText(f.key, text[f.key]), profile.defaults[f.key]);
          const label = (
            <span className="flex flex-wrap items-center gap-2">
              {f.label}
              {overridden ? <Badge tone="warning">đã sửa</Badge> : null}
              {!isDefault ? (
                <button
                  type="button"
                  className="text-[12px] font-normal text-accent hover:underline"
                  onClick={() => setText((t) => ({ ...t, [f.key]: toText(f.key, profile.defaults[f.key]) }))}
                >
                  dùng mặc định
                </button>
              ) : null}
            </span>
          );
          const common = {
            value: text[f.key],
            onChange: (e: { target: { value: string } }) => setText((t) => ({ ...t, [f.key]: e.target.value })),
            spellCheck: false,
            hint: f.hint,
          };
          if (f.kind === "via")
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <span className="text-[14px] font-medium">{label}</span>
                <Segmented<string>
                  aria-label={f.label}
                  size="sm"
                  value={text[f.key]}
                  onChange={(v) => setText((t) => ({ ...t, [f.key]: v }))}
                  options={[
                    { value: "route", label: "Theo cách lấy hàng" },
                    { value: "skip", label: "Không đọc trang" },
                  ]}
                />
                <span className="text-[13px] text-ink-2">{f.hint}</span>
              </div>
            );
          if (f.kind === "text" || f.kind === "csv" || f.kind === "number")
            return (
              <Input
                key={f.key}
                aria-label={f.label}
                label={label}
                inputMode={f.kind === "number" ? "numeric" : undefined}
                placeholder={f.placeholder}
                className="font-mono text-[13px]"
                {...common}
              />
            );
          return (
            <Textarea
              key={f.key}
              aria-label={f.label}
              label={label}
              rows={f.kind === "long" ? 3 : Math.min(6, Math.max(2, text[f.key].split("\n").length))}
              className={f.kind === "long" ? "text-[13px]" : "font-mono text-[13px]"}
              {...common}
            />
          );
        })}
        <div className="flex flex-wrap gap-2">
          <Button onClick={onSave} loading={save.isPending} disabled={!changed.length}>
            Lưu cấu hình
          </Button>
          <Button variant="ghost" icon={<RotateCcw className="size-4" aria-hidden />} onClick={onReset} loading={reset.isPending} disabled={!n}>
            Khôi phục mặc định
          </Button>
        </div>
        <TryBox platform={profile.platform} draft={draft} />
      </div>
    </details>
  );
}

function TryBox({ platform, draft }: { platform: string; draft: Record<string, unknown> }) {
  const [url, setUrl] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const run = useTrySourceProfile();
  const [result, setResult] = useState<SourceProfileTry | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onTry() {
    setError(null);
    try {
      setResult(
        await run.mutateAsync({
          url: url.trim(),
          image_url: imageUrl.trim() || null,
          ...(Object.keys(draft).length ? { platform, fields: draft } : {}),
        }),
      );
    } catch (e) {
      setResult(null);
      setError(errorMessage(e));
    }
  }

  return (
    <section aria-label="Thử với một link" className="flex flex-col gap-2 rounded-md bg-soft/60 p-3">
      <h3 className="text-[15px]">Thử với một link</h3>
      <p className="text-[13px] text-ink-2">
        Dán link sản phẩm (và nếu muốn, một link ảnh) để xem hệ thống nhận ra gì{Object.keys(draft).length ? " theo bản chị đang sửa" : ""}. Chỉ
        tính trên máy chủ, không gọi AI, không mở trang.
      </p>
      <Input label="Link sản phẩm" value={url} onChange={(e) => setUrl(e.target.value)} spellCheck={false} placeholder="https://…" />
      <Input
        label="Link ảnh (không bắt buộc)"
        value={imageUrl}
        onChange={(e) => setImageUrl(e.target.value)}
        spellCheck={false}
        placeholder="https://…/anh-nho.jpg"
      />
      <div>
        <Button variant="secondary" icon={<FlaskConical className="size-4" aria-hidden />} onClick={onTry} loading={run.isPending} disabled={!url.trim()}>
          Thử
        </Button>
      </div>
      {error ? <p className="text-[14px] text-seal">{error}</p> : null}
      {result ? (
        <dl aria-label="Kết quả thử" className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
          <dt className="text-ink-2">Nguồn</dt>
          <dd>{result.label}</dd>
          <dt className="text-ink-2">Mã món</dt>
          <dd className="font-mono">{result.id ?? "— (không khớp mẫu link nào)"}</dd>
          <dt className="text-ink-2">Link chuẩn</dt>
          <dd className="break-all font-mono">{result.canonical_url}</dd>
          {result.fetch_via === "skip" ? (
            <>
              <dt className="text-ink-2">Đọc trang</dt>
              <dd>Không đọc (đã đặt «Không đọc trang»)</dd>
            </>
          ) : null}
          {result.image ? (
            <>
              <dt className="text-ink-2">Ảnh lớn</dt>
              <dd className="break-all font-mono">{result.image.output}</dd>
              <dt className="text-ink-2">Máy chủ ảnh</dt>
              <dd className={result.image.allowed ? "text-auto" : "text-seal"}>
                {result.image.allowed ? "hợp lệ" : "không thuộc máy chủ ảnh của sàn — ảnh này sẽ bị bỏ"}
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </section>
  );
}
