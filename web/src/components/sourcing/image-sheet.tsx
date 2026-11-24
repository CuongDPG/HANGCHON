"use client";

import { Camera, ImagePlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button, ImageBox, Input, Sheet, notifyError } from "@/components/ui";
import { useImageSearch, useRun } from "@/lib/api/sourcing";
import { RunProgress } from "./run-progress";

const MAX_BYTES = 8 * 1024 * 1024;

/** a3 — Chụp hoặc chọn ảnh một món: AI nhận ra món, sinh từ khoá ba thứ tiếng rồi tìm đúng mẫu. */
export function ImageSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const search = useImageSearch();
  const run = useRun(runId);
  const r = run.data;
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  useEffect(() => () => (preview ? URL.revokeObjectURL(preview) : undefined), [preview]);
  useEffect(() => {
    const bid = r?.status === "succeeded" ? (r.progress?.brief_id ?? r.brief_id) : undefined;
    if (bid) router.push(`/desk/san-hang/de/${bid}`);
  }, [r, router]);

  function pick(f: File | undefined) {
    if (!f) return;
    if (!f.type.startsWith("image/")) return notifyError("Chị chọn tệp ảnh nhé.");
    if (f.size > MAX_BYTES) return notifyError("Ảnh lớn quá 8 MB, chị chọn ảnh nhỏ hơn.");
    setFile(f);
  }

  function close() {
    setFile(null);
    setNote("");
    setRunId(null);
    onClose();
  }

  return (
    <Sheet
      open={open}
      onClose={close}
      title="Tìm bằng ảnh"
      description="Chụp món thấy ngoài đời hoặc ảnh chụp màn hình. AI tìm đúng mẫu và các xưởng bán cùng mẫu."
      footer={
        <Button
          block
          icon={<ImagePlus className="size-4" />}
          disabled={!file || !!runId}
          loading={search.isPending}
          onClick={() => file && search.mutate({ file, note }, { onSuccess: (res) => setRunId(res.id), onError: notifyError })}
        >
          Tìm món này
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <label className="block cursor-pointer">
          <span className="sr-only">Chọn ảnh</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            className="sr-only"
            onChange={(e) => pick(e.target.files?.[0])}
          />
          {preview ? (
            <ImageBox src={preview} alt="Ảnh chị chọn" ratio="4/3" />
          ) : (
            <div className="grid aspect-[4/3] place-items-center rounded-md border border-dashed border-line-strong bg-soft text-ink-2">
              <span className="flex flex-col items-center gap-2 text-sm">
                <Camera className="size-6" aria-hidden />
                Chạm để chụp hoặc chọn ảnh
              </span>
            </div>
          )}
        </label>
        <Input label="Ghi kèm (không bắt buộc)" placeholder="vd. giá phơi ở ban công nhà bạn" value={note} onChange={(e) => setNote(e.target.value)} />
        {r ? <RunProgress run={r} /> : null}
      </div>
    </Sheet>
  );
}
