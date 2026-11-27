"use client";

import { Clapperboard, Music, Trash2, Upload } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  IconButton,
  InlineSelect,
  Input,
  PageHeader,
  SectionLabel,
  Segmented,
  SkeletonList,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { useApproveVideo, useDeleteMedia, useMedia, usePickProducts, usePlanVideo, useUploadClip, type MediaAsset } from "@/lib/api/content";
import { formatDateTime } from "@/lib/format";
import { CONTENT_SECTIONS } from "@/lib/desk-sections";
import { CONTENT_SETTINGS, localFile } from "./shared";

/** Dựng video ngắn (f6): clip chị quay khi thử hàng → AI lập kế hoạch dựng → dựng file 9:16 (nếu máy có ffmpeg) → chị duyệt. */
export function VideoScreen() {
  const { data, isPending, error } = useMedia();
  const products = usePickProducts();
  const [productId, setProductId] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [seconds, setSeconds] = useState<"20" | "24" | "30">("24");
  const [notes, setNotes] = useState("");
  const plan = usePlanVideo();
  const all = useMemo(() => data?.items ?? [], [data]);
  const clips = all.filter((m) => m.purpose === "trial_clip" && (!productId || m.product_id === productId));
  const videos = all.filter((m) => m.purpose === "edited_video");
  const options = (products.data?.items ?? []).map((p) => ({ value: p.id, label: p.name }));

  return (
    <div className="flex flex-col gap-4">
      <PageHeader sections={CONTENT_SECTIONS} active="video" settings={CONTENT_SETTINGS} />
      <InlineSelect label="Món" value={productId} onChange={(v) => { setProductId(v); setPicked([]); }} options={options} placeholder="Chọn món để lọc clip" />
      <UploadCard productId={productId} />

      <section className="flex flex-col gap-2">
        <SectionLabel>CLIP THỬ HÀNG</SectionLabel>
        {isPending ? (
          <SkeletonList rows={3} />
        ) : error ? (
          <EmptyState tone="error" title="Chưa tải được clip" description={error.message} />
        ) : clips.length === 0 ? (
          <EmptyState icon={<Clapperboard />} title="Chưa có clip" description="Tải vài clip ngắn chị quay lúc dùng thử (bàn tay, món hàng), ghi vài chữ mô tả từng clip." />
        ) : (
          <ul className="grid gap-2 md:grid-cols-2">
            {clips.map((c) => (
              <ClipRow key={c.id} clip={c} checked={picked.includes(c.id)} onToggle={(on) => setPicked((x) => (on ? [...x, c.id] : x.filter((i) => i !== c.id)))} />
            ))}
          </ul>
        )}
      </section>

      {clips.length ? (
        <Card tone="soft" className="flex flex-col gap-3">
          <p className="text-[14px]">
            Đã chọn <b>{picked.length}</b> clip{picked.length ? " (theo thứ tự chọn)" : ""}.
          </p>
          <Segmented aria-label="Độ dài video" value={seconds} onChange={setSeconds} options={[{ value: "20", label: "20 giây" }, { value: "24", label: "24 giây" }, { value: "30", label: "30 giây" }]} />
          <Input label="Ý của chị (không bắt buộc)" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Vd: mở bằng cảnh rót trà" />
          <Button
            disabled={!picked.length}
            loading={plan.isPending}
            icon={<Clapperboard className="size-4" aria-hidden />}
            onClick={() =>
              plan.mutate(
                { product_id: productId, clip_ids: picked, notes: notes || undefined, target_seconds: Number(seconds) },
                { onSuccess: (v) => { notifySuccess(v.edit_spec.render === "unavailable" ? "AI đã lập kế hoạch dựng" : "AI đang dựng video"); setPicked([]); } },
              )
            }
          >
            Dựng video
          </Button>
        </Card>
      ) : null}

      <section className="flex flex-col gap-2">
        <SectionLabel>VIDEO AI DỰNG</SectionLabel>
        {videos.length === 0 ? (
          <p className="text-[14px] text-ink-2">Chưa có video nào.</p>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {videos.map((v) => (
              <VideoCard key={v.id} video={v} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function UploadCard({ productId }: { productId: string | null }) {
  const upload = useUploadClip();
  const ref = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <span className="text-[14px] font-medium">Tải clip</span>
        <label
          htmlFor="clip-file"
          className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-dashed border-line-strong bg-surface px-3 py-2 text-[14px] hover:border-ink-3"
        >
          <Clapperboard className="size-4 shrink-0 text-accent" aria-hidden />
          <span className="min-w-0 flex-1 truncate">{file ? file.name : "Chọn clip quay khi thử hàng (mp4, mov)"}</span>
        </label>
        <input
          id="clip-file"
          ref={ref}
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="sr-only"
        />
      </div>
      <Input label="Clip này quay gì?" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Vd: rót trà nóng, tháo nắp rửa" hint="AI không xem được hình, chỉ dựa vào mô tả này để chọn đoạn." />
      <Button
        variant="secondary"
        icon={<Upload className="size-4" aria-hidden />}
        disabled={!file}
        loading={upload.isPending}
        onClick={() =>
          file &&
          upload.mutate(
            { file, productId: productId ?? undefined, note: note || undefined },
            { onSuccess: () => { notifySuccess("Đã tải clip"); setFile(null); setNote(""); if (ref.current) ref.current.value = ""; } },
          )
        }
      >
        Tải lên{productId ? "" : " (chưa gắn món)"}
      </Button>
    </Card>
  );
}

function ClipRow({ clip, checked, onToggle }: { clip: MediaAsset; checked: boolean; onToggle: (on: boolean) => void }) {
  const del = useDeleteMedia();
  const confirm = useConfirm();
  const { user: session } = useSession();
  return (
    <li className="flex gap-3 rounded-md border border-line bg-surface p-2.5">
      <video src={localFile(clip.url) ?? undefined} preload="metadata" muted playsInline className="h-20 w-14 shrink-0 rounded-sm bg-ink object-cover" />
      <div className="min-w-0 flex-1">
        <Checkbox label={clip.transcript || "Clip chưa có mô tả"} description={`${clip.duration_seconds ?? "?"} giây · ${clip.product_name ?? "chưa gắn món"}`} checked={checked} onChange={(e) => onToggle(e.target.checked)} />
      </div>
      {session?.role === "owner" ? (
        <IconButton
          label="Xoá clip"
          icon={<Trash2 />}
          onClick={async () => {
            if (await confirm({ title: "Xoá clip này?", confirmLabel: "Xoá", tone: "danger" })) del.mutate(clip.id);
          }}
        />
      ) : null}
    </li>
  );
}

const VIDEO_STATUS: Record<string, { label: string; tone: "accent" | "warning" | "success" | "danger" | "neutral" }> = {
  processing: { label: "Đang dựng…", tone: "accent" },
  pending_review: { label: "Chờ chị xem", tone: "warning" },
  approved: { label: "Đã duyệt", tone: "success" },
  failed: { label: "Lỗi", tone: "danger" },
};

function VideoCard({ video }: { video: MediaAsset }) {
  const approve = useApproveVideo();
  const { user: session } = useSession();
  const st = VIDEO_STATUS[video.status] ?? { label: video.status, tone: "neutral" as const };
  const spec = video.edit_spec;
  const rendered = spec.render === "done" && video.url;
  return (
    <li>
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{video.product_name ?? "Video ngắn"}</span>
          <Badge tone={st.tone}>{st.label}</Badge>
          <span className="flex-1" />
          <span className="text-[12.5px] text-ink-3">{formatDateTime(video.created_at)}</span>
        </div>
        {rendered ? (
          <video src={localFile(video.url) ?? undefined} controls playsInline className="mx-auto aspect-[9/16] max-h-[420px] rounded-md bg-ink" />
        ) : spec.render_note ? (
          <p className="rounded-md bg-review-wash p-2.5 text-[13px] text-review">{spec.render_note}</p>
        ) : null}
        {spec.summary ? <p className="text-[14px]">{spec.summary}</p> : null}
        {spec.segments?.length ? (
          <ol className="flex flex-col gap-1 text-[13px]">
            {spec.segments.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="w-16 shrink-0 text-ink-3 tabular-nums">
                  {s.start.toFixed(1)}–{s.end.toFixed(1)}s
                </span>
                <span>«{s.caption}»</span>
              </li>
            ))}
          </ol>
        ) : null}
        {spec.music ? (
          <p className="flex items-start gap-1.5 text-[13px] text-ink-2">
            <Music className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            Nhạc: {spec.music.mood} — {spec.music.suggestion}
          </p>
        ) : null}
        {session?.role === "owner" && video.status === "pending_review" ? (
          <Button loading={approve.isPending} onClick={() => approve.mutate(video.id, { onSuccess: () => notifySuccess("Đã duyệt video, gắn vào bản TikTok") })}>
            {rendered ? "Duyệt video" : "Duyệt kế hoạch dựng"}
          </Button>
        ) : null}
        <p className="text-[12px] text-ink-3">Có phần do AI dựng — sẽ gắn nhãn khi đăng.</p>
      </Card>
    </li>
  );
}
