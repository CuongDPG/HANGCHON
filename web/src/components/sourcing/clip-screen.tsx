"use client";

import { Check, ExternalLink, Send } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Brand } from "@/components/layout/brand";
import { Badge, Button, ButtonLink, Card, EmptyState, ImageBox, InlineSelect, Skeleton } from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { isRunActive, useBriefs, useClip, useClipMatch, useRun } from "@/lib/api/sourcing";
import { CLIP_PATH, readClipHash } from "@/lib/clipper/bookmarklet";
import { formatNumber } from "@/lib/format";
import { RunProgress } from "./run-progress";

const STORE = "hc_clip";
const LOOSE = "le";

/** Dữ liệu nút gửi sang ở phần `#` → giữ trong sessionStorage (qua được bước đăng nhập), rồi xoá `#` khỏi thanh địa chỉ. */
function useClipData() {
  const [state, setState] = useState<{ data: Record<string, unknown> | null | undefined; version: number }>({ data: undefined, version: 0 });
  useEffect(() => {
    const setData = (data: Record<string, unknown> | null) => setState((p) => ({ data, version: p.version + 1 }));
    const read = () => {
      const fromHash = readClipHash(window.location.hash);
      if (fromHash) {
        sessionStorage.setItem(STORE, encodeURIComponent(JSON.stringify(fromHash)));
        window.history.replaceState(null, "", window.location.pathname);
        setData(fromHash);
        return;
      }
      setData(readClipHash(sessionStorage.getItem(STORE) ?? ""));
    };
    read();
    window.addEventListener("hashchange", read); // cửa sổ đang mở, chị bấm nút ở trang khác → chỉ đổi phần #
    return () => window.removeEventListener("hashchange", read);
  }, []);
  return state;
}

const s = (v: unknown) => (typeof v === "string" ? v : "");
const n = (v: unknown) => (typeof v === "number" && isFinite(v) ? v : null);

/**
 * Cửa sổ nhỏ mở từ nút «Gửi sang Hàng Chọn» (bookmarklet, `lib/clipper`): xem nhanh trang chị vừa gửi rồi lưu thành
 * ứng viên — cập nhật món đã có (cùng sàn + mã món) hoặc thêm vào một đề / ứng viên lẻ. Ngoài khung desk (không menu).
 */
export function ClipScreen() {
  const { data, version } = useClipData();
  const { status } = useSession();

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col gap-4 px-4 py-5">
      <div className="flex items-center justify-between gap-3">
        <Brand sub="Bàn làm việc" />
        <h1 className="text-[18px] font-bold">Gửi sang Hàng Chọn</h1>
      </div>
      {data === undefined || status === "loading" ? (
        <Skeleton className="h-64 w-full" />
      ) : status === "unauthenticated" ? (
        <EmptyState
          title="Chị chưa đăng nhập bàn làm việc"
          action={<ButtonLink href={`/desk/dang-nhap?next=${encodeURIComponent(CLIP_PATH)}`}>Đăng nhập</ButtonLink>}
        />
      ) : status === "error" ? (
        <EmptyState tone="error" title="Chưa kết nối được máy chủ" />
      ) : !data ? (
        <EmptyState title="Chưa có trang nào" description="Mở trang món trên sàn rồi bấm nút «Gửi sang Hàng Chọn»." />
      ) : s(data.error) ? (
        <EmptyState tone="error" title="Chưa đọc được trang này" description={s(data.error)} />
      ) : (
        <ClipForm key={version} data={data} />
      )}
    </main>
  );
}

function ClipForm({ data }: { data: Record<string, unknown> }) {
  const url = s(data.url);
  const title = s(data.title);
  const images = Array.isArray(data.images) ? data.images.filter((u): u is string => typeof u === "string") : [];
  const specs = data.specs && typeof data.specs === "object" ? Object.keys(data.specs).length : 0;
  const variants = Array.isArray(data.variants) ? data.variants.length : 0;
  const match = useClipMatch(url.startsWith("https://") ? url : null);
  const briefs = useBriefs("active");
  const [brief, setBrief] = useState<string>(LOOSE);
  const [runId, setRunId] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const clip = useClip();
  const run = useRun(runId);
  const r = run.data;
  const existing = match.data?.candidate_id ?? null;
  const savedId = r?.status === "succeeded" ? r.progress?.candidate_ids?.[0] : undefined;
  const qc = useQueryClient();
  useEffect(() => {
    if (savedId) qc.invalidateQueries({ queryKey: ["sourcing"] }); // lần gửi sau cùng món → «Cập nhật ứng viên»
  }, [savedId, qc]);

  const facts = [
    n(data.rating) !== null ? `${n(data.rating)}★` : null,
    n(data.review_count) !== null ? `${formatNumber(n(data.review_count)!)} đánh giá` : null,
    n(data.sales_count) !== null ? `đã bán ${formatNumber(n(data.sales_count)!)}` : null,
    n(data.moq) !== null ? `tối thiểu ${formatNumber(n(data.moq)!)}` : null,
    specs ? `${specs} thông số` : null,
    variants ? `${variants} phân loại` : null,
  ].filter(Boolean);

  function save() {
    const body: Record<string, unknown> = { ...data };
    delete body.site;
    if (!existing && brief !== LOOSE) body.brief_id = brief;
    setUpdating(!!existing);
    clip.mutate(body, { onSuccess: (res) => setRunId(res.id) });
  }

  return (
    <>
      <Card className="flex flex-col gap-3 border border-line">
        <div className="flex flex-wrap items-center gap-2">
          {match.data ? <Badge tone="outline">{match.data.platform_label}</Badge> : null}
          {match.data?.external_id && match.data.platform !== "web" ? <span className="text-[12.5px] text-ink-3">mã {match.data.external_id}</span> : null}
          <a href={url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-[13px] text-accent hover:underline">
            Trang gốc <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
        <h2 className="text-[16px] leading-snug font-semibold [overflow-wrap:anywhere]">{title || "Không thấy tên món trên trang"}</h2>
        <p className="text-[15px]">
          {s(data.price) ? (
            <strong className="font-display text-[20px]">
              {formatNumber(Number(s(data.price)))} {s(data.currency)}
            </strong>
          ) : (
            <span className="text-ink-3">Không thấy giá</span>
          )}
          {facts.length ? <span className="text-[13px] text-ink-2"> · {facts.join(" · ")}</span> : null}
        </p>
        {s(data.seller_name) ? <p className="text-[13px] text-ink-2">Người bán: {s(data.seller_name)}</p> : null}
        {images.length ? (
          <ul className="grid grid-cols-5 gap-1.5" aria-label={`${images.length} ảnh`}>
            {images.slice(0, 12).map((u) => (
              <li key={u}>
                <ImageBox src={u} alt="" ratio="1/1" placeholder="" referrerPolicy="no-referrer" />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-ink-3">Không thấy ảnh</p>
        )}
      </Card>

      {savedId ? (
        <Card tone="soft" className="flex flex-col gap-3" role="status">
          <p className="flex items-center gap-2 text-[15px] font-semibold text-auto">
            <Check className="size-4" aria-hidden /> {updating ? "Đã cập nhật ứng viên" : "Đã thêm ứng viên"}
          </p>
          <div className="flex gap-2">
            <ButtonLink href={`/desk/san-hang/ung-vien/${savedId}`} target="_blank" size="sm">
              Mở hồ sơ
            </ButtonLink>
            <Button size="sm" variant="secondary" onClick={() => window.close()}>
              Đóng cửa sổ
            </Button>
          </div>
        </Card>
      ) : r ? (
        <RunProgress run={r} />
      ) : null}

      {!runId || r?.status === "failed" ? (
        <div className="flex flex-col gap-3">
          {match.isPending ? (
            <Skeleton className="h-10 w-full" />
          ) : existing ? (
            <p className="text-[14px]">
              Đã có ứng viên:{" "}
              <a href={`/desk/san-hang/ung-vien/${existing}`} target="_blank" rel="noreferrer" className="font-semibold text-accent hover:underline">
                {match.data?.candidate_title}
              </a>
            </p>
          ) : (
            <InlineSelect
              label="Lưu vào"
              value={brief}
              onChange={setBrief}
              options={[{ value: LOOSE, label: "Ứng viên lẻ (không thuộc đề)" }, ...(briefs.data?.items ?? []).map((b) => ({ value: b.id, label: b.title }))]}
            />
          )}
          <Button block icon={<Send className="size-4" aria-hidden />} disabled={!title || match.isPending} loading={clip.isPending || (!!r && isRunActive(r))} onClick={save}>
            {existing ? "Cập nhật ứng viên" : brief === LOOSE ? "Thêm ứng viên lẻ" : "Thêm vào đề"}
          </Button>
        </div>
      ) : null}
    </>
  );
}
