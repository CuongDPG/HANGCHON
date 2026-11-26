"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink, ImageDown, ImageIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Badge, Button, IconButton, ImageBox, Sheet, notifyError, notifySuccess } from "@/components/ui";
import { cn } from "@/lib/cn";
import { isDetailFetchActive, useCandidateGallery, useFetchDetails, type CandidateGallery, type GalleryImage } from "@/lib/api/sourcing";

/**
 * Ảnh nhà cung cấp của một ứng viên — chỉ ở desk (phía chọn hàng), để chị hình dung món hàng; link gốc vẫn mở được.
 * Ảnh đã lưu bản sao về kho riêng thì hiện bản đó, chưa lưu thì hiện link gốc (không gửi Referer để CDN không chặn).
 * Không có ảnh: ô giữ chỗ «Chưa có ảnh — Lấy ảnh và chi tiết».
 */
export function SupplierGallery({ candidateId, className, heading = true }: { candidateId: string; className?: string; heading?: boolean }) {
  const { data, isPending, error } = useCandidateGallery(candidateId);
  const fetchDetails = useFetchDetails(candidateId);
  const [open, setOpen] = useState<number | null>(null);
  useRefreshWhenFetched(data);

  const busy = isDetailFetchActive(data) || fetchDetails.isPending;
  const images = data?.images ?? [];
  const start = () =>
    fetchDetails.mutate(undefined, {
      onSuccess: () => notifySuccess("Đang đọc trang nguồn, ảnh sẽ hiện khi xong (khoảng 1 phút)."),
      onError: notifyError,
    });
  const notCached = images.filter((i) => !i.cached).length;

  return (
    <section className={cn("flex flex-col gap-2", className)} aria-label="Ảnh nhà cung cấp">
      {heading ? (
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-[15px] font-semibold">
            Ảnh nhà cung cấp{images.length ? <span className="font-normal text-ink-3"> · {images.length}</span> : null}
          </h2>
          {images.length && data?.source_url ? (
            <Button size="sm" variant="ghost" onClick={start} loading={busy} icon={<ImageDown className="size-4" aria-hidden />}>
              {busy ? "Đang lấy…" : "Lấy lại ảnh và chi tiết"}
            </Button>
          ) : null}
        </div>
      ) : null}
      {isPending ? (
        <div className="grid grid-cols-4 gap-2 md:grid-cols-6" aria-hidden>
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="aspect-square animate-pulse rounded-md bg-soft-2" />
          ))}
        </div>
      ) : error ? (
        <p className="text-[13px] text-danger">Chưa tải được ảnh: {error.message}</p>
      ) : images.length === 0 ? (
        <button
          type="button"
          onClick={start}
          disabled={busy || !data?.source_url}
          className="grid min-h-28 w-full place-items-center rounded-md border border-dashed border-line-strong bg-[repeating-linear-gradient(135deg,transparent_0_10px,var(--color-soft)_10px_11px)] px-4 py-5 text-center text-ink-2 hover:border-ink-3 hover:text-ink disabled:cursor-default"
        >
          <span className="flex flex-col items-center gap-1.5 text-[14px]">
            <ImageIcon className="size-6" strokeWidth={1.6} aria-hidden />
            {busy ? "Đang lấy ảnh và chi tiết…" : data?.source_url ? "Chưa có ảnh — Lấy ảnh và chi tiết" : "Chưa có ảnh (ứng viên không có link nguồn)"}
          </span>
        </button>
      ) : (
        <ul className="grid grid-cols-4 gap-2 md:grid-cols-6">
          {images.map((img, i) => (
            <li key={img.source_url}>
              <button type="button" onClick={() => setOpen(i)} className="block w-full rounded-md focus-visible:outline-2 focus-visible:outline-accent" aria-label={`Xem ảnh ${i + 1} lớn`}>
                <ImageBox src={img.src} alt="" ratio="1/1" placeholder="" referrerPolicy="no-referrer" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <StatusLine gallery={data} notCached={notCached} />
      <GalleryLightbox images={images} index={open} onIndex={setOpen} title={data?.title_vi ?? "Ảnh nhà cung cấp"} />
    </section>
  );
}

function StatusLine({ gallery, notCached }: { gallery?: CandidateGallery; notCached: number }) {
  const st = gallery?.detail_fetch;
  if (!gallery) return null;
  if (st?.status === "queued" || st?.status === "running")
    return <p className="text-[13px] text-ink-2">Đang đọc trang nguồn và lưu ảnh về máy…</p>;
  if (st?.status === "failed")
    return <p className="text-[13px] text-danger [text-wrap:pretty]">Lần lấy gần nhất chưa được: {st.error}</p>;
  if (st?.note) return <p className="text-[13px] text-ink-2">{st.note}</p>;
  if (gallery.images.length && notCached)
    return (
      <p className="text-[12.5px] text-ink-3">
        {notCached} ảnh đang hiện bằng link gốc của sàn (chưa lưu bản sao về máy) — bấm «Lấy lại ảnh và chi tiết» để lưu.
      </p>
    );
  return gallery.images.length ? <p className="text-[12.5px] text-ink-3">Ảnh chỉ hiện ở bàn làm việc, không lên website.</p> : null;
}

/** Xong một lượt «Lấy ảnh và chi tiết» → làm mới danh sách/bảng chọn/hồ sơ để ảnh thu nhỏ hiện ngay. */
function useRefreshWhenFetched(data?: CandidateGallery) {
  const qc = useQueryClient();
  const wasActive = useRef(false);
  const active = isDetailFetchActive(data);
  useEffect(() => {
    if (wasActive.current && !active) {
      for (const key of ["sourcing", "selection", "assessment", "catalog"]) qc.invalidateQueries({ queryKey: [key] });
    }
    wasActive.current = active;
  }, [active, qc]);
}

/** Xem ảnh lớn, chuyển ảnh trước/sau, mở link ảnh gốc. */
export function GalleryLightbox({
  images,
  index,
  onIndex,
  title,
}: {
  images: GalleryImage[];
  index: number | null;
  onIndex: (i: number | null) => void;
  title: string;
}) {
  const img = index !== null ? images[index] : undefined;
  const n = images.length;
  return (
    <Sheet open={!!img} onClose={() => onIndex(null)} title={title} description={img ? `Ảnh ${index! + 1}/${n}` : undefined} size="lg">
      {img ? (
        <div className="flex flex-col gap-3">
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- ảnh nhà cung cấp từ kho riêng hoặc link gốc */}
            <img src={img.src} alt={`${title} — ảnh ${index! + 1}`} referrerPolicy="no-referrer" className="mx-auto max-h-[62dvh] w-auto rounded-md bg-soft-2 object-contain" />
            {n > 1 ? (
              <>
                <IconButton label="Ảnh trước" icon={<ChevronLeft />} onClick={() => onIndex((index! - 1 + n) % n)} className="absolute top-1/2 left-1 -translate-y-1/2 bg-surface/90" />
                <IconButton label="Ảnh sau" icon={<ChevronRight />} onClick={() => onIndex((index! + 1) % n)} className="absolute top-1/2 right-1 -translate-y-1/2 bg-surface/90" />
              </>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            {img.cached ? <Badge tone="success">Đã lưu bản sao</Badge> : <Badge tone="outline">Link gốc, chưa lưu</Badge>}
            {img.error ? <span className="text-ink-3">Lưu chưa được: {img.error}</span> : null}
            <a href={img.source_url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-accent hover:underline">
              Mở ảnh gốc <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </div>
        </div>
      ) : null}
    </Sheet>
  );
}

/** Ảnh thu nhỏ bấm được (bảng so sánh): mở xem mọi ảnh nhà cung cấp của ứng viên. */
export function CandidateThumb({ candidateId, src, count, title, className }: { candidateId: string; src: string | null; count: number; title: string; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={cn("relative block shrink-0 rounded-md", className)} aria-label={`Xem ảnh nhà cung cấp: ${title}`}>
        <ImageBox src={src} alt="" ratio="1/1" placeholder="" referrerPolicy="no-referrer" />
        {count > 1 ? <span className="absolute right-0.5 bottom-0.5 rounded-sm bg-ink/75 px-1 text-[11px] text-paper tabular-nums">{count}</span> : null}
      </button>
      {open ? <ThumbSheet candidateId={candidateId} title={title} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function ThumbSheet({ candidateId, title, onClose }: { candidateId: string; title: string; onClose: () => void }) {
  return (
    <Sheet open onClose={onClose} title={title} size="lg">
      <SupplierGallery candidateId={candidateId} />
    </Sheet>
  );
}
