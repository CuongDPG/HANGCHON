"use client";

import { ArrowDown, ArrowUp, ImagePlus, Star, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { useConfirm } from "@/components/ui/confirm";
import { IconButton } from "@/components/ui/icon-button";
import { ImageBox } from "@/components/ui/image-box";
import { Spinner } from "@/components/ui/button";
import { notifyError, notifySuccess } from "@/components/ui/toast";
import { deskProductApi, useProductMutation, type DeskProduct } from "@/lib/api/catalog";
import { api } from "@/lib/api/client";

/** Ảnh sản phẩm (e6): tải lên → tự xoay, cân sáng, cắt vuông giữ món ở giữa; sắp thứ tự, đặt ảnh bìa. */
export function ImageManager({ product }: { product: DeskProduct }) {
  const input = useRef<HTMLInputElement>(null);
  const confirm = useConfirm();
  const [uploading, setUploading] = useState(0);
  const id = product.id;
  const order = useProductMutation(id, (ids: string[]) => deskProductApi.order(id, ids));
  const primary = useProductMutation(id, (imageId: string) => deskProductApi.primary(id, imageId));
  const remove = useProductMutation(id, async (imageId: string) => {
    await deskProductApi.removeImage(id, imageId);
    return api.get<DeskProduct>(`/api/desk/catalog/products/${id}`);
  });
  const upload = useProductMutation(id, (file: File) => deskProductApi.upload(id, file));
  const images = product.images;

  async function onFiles(files: FileList | null) {
    if (!files?.length) return;
    const list = Array.from(files);
    setUploading(list.length);
    for (const f of list) {
      try {
        await upload.mutateAsync(f);
      } catch {
        /* lỗi đã hiện toast */
      } finally {
        setUploading((n) => n - 1);
      }
    }
    if (input.current) input.current.value = "";
    notifySuccess("Đã xử lý ảnh: xoay đúng chiều, cân sáng, cắt vuông.");
  }

  function move(i: number, delta: number) {
    const ids = images.map((x) => x.id);
    const j = i + delta;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    order.mutate(ids);
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {images.map((img, i) => (
          <li key={img.id} className="flex flex-col gap-1.5">
            <ImageBox
              src={img.src_small ?? img.src}
              alt={img.alt ?? product.name}
              ratio="1/1"
              placeholder={img.status === "processing" ? "Chờ chị duyệt xử lý ảnh" : "Đang xử lý"}
              overlay={img.is_primary ? <Badge tone="accent">Ảnh bìa</Badge> : null}
            />
            <div className="flex items-center justify-between">
              <IconButton size="sm" label="Lên trước" icon={<ArrowUp />} disabled={i === 0} onClick={() => move(i, -1)} />
              <IconButton size="sm" label="Ra sau" icon={<ArrowDown />} disabled={i === images.length - 1} onClick={() => move(i, 1)} />
              <IconButton
                size="sm"
                label="Đặt làm ảnh bìa"
                icon={<Star className={img.is_primary ? "fill-current text-accent" : undefined} />}
                disabled={img.is_primary}
                onClick={() => primary.mutate(img.id)}
              />
              <IconButton
                size="sm"
                label="Xoá ảnh"
                icon={<Trash2 />}
                onClick={async () => {
                  if (await confirm({ title: "Xoá ảnh này?", message: "Ảnh gốc và các cỡ đã xử lý đều bị xoá.", confirmLabel: "Xoá", tone: "danger" }))
                    remove.mutate(img.id, { onError: notifyError });
                }}
              />
            </div>
          </li>
        ))}
        <li>
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={uploading > 0}
            className="grid aspect-square w-full place-items-center rounded-md border border-dashed border-line-strong text-ink-2 hover:border-ink-3 hover:text-ink"
          >
            <span className="flex flex-col items-center gap-1.5 text-[14px]">
              {uploading > 0 ? <Spinner className="size-5" /> : <ImagePlus className="size-6" aria-hidden />}
              {uploading > 0 ? `Đang xử lý ${uploading} ảnh…` : "Thêm ảnh chị chụp"}
            </span>
          </button>
          <input ref={input} type="file" accept="image/*" multiple className="sr-only" onChange={(e) => onFiles(e.target.files)} aria-label="Chọn ảnh" />
        </li>
      </ul>
      <p className="text-[13px] text-ink-3">
        Chỉ chỉnh ảnh thật: xoay theo EXIF, cân sáng nhẹ, cắt vuông giữ món ở giữa, tạo bản webp. Không tạo ảnh giả. Hoàn tác được trong Nhật ký AI.
      </p>
    </div>
  );
}
