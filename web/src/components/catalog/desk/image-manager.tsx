"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, ImagePlus, Images, Star, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/choice";
import { useConfirm } from "@/components/ui/confirm";
import { IconButton } from "@/components/ui/icon-button";
import { ImageBox } from "@/components/ui/image-box";
import { Button, Spinner } from "@/components/ui/button";
import { Sheet } from "@/components/ui/overlay";
import { notifyError, notifySuccess } from "@/components/ui/toast";
import { useSession } from "@/lib/api/auth";
import { deskProductApi, useProductMutation, useSupplierImageOptions, type DeskProduct } from "@/lib/api/catalog";
import { cn } from "@/lib/cn";
import { api } from "@/lib/api/client";

const CLEAN_BG = "catalog.image_clean_background";

/** Bật/tắt làm sạch nền (cài đặt chung, áp cho ảnh tải lên sau đó). Chỉ chị đổi được. */
function CleanBackgroundSwitch() {
  const qc = useQueryClient();
  const { user } = useSession();
  const settings = useQuery({
    queryKey: ["control", "settings"],
    queryFn: () => api.get<{ key: string; value: unknown }[]>("/api/desk/control/settings"),
  });
  const save = useMutation({
    mutationFn: (v: boolean) => api.patch(`/api/desk/control/settings/${CLEAN_BG}`, { value: v }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["control", "settings"] });
      notifySuccess(v ? "Ảnh mới sẽ được làm sạch nền" : "Đã tắt làm sạch nền cho ảnh mới");
    },
    onError: notifyError,
  });
  const value = settings.data?.find((s) => s.key === CLEAN_BG)?.value;
  if (settings.isPending || value === undefined) return null;
  return (
    <Switch
      label="Làm sạch nền sáng"
      description="Nền trắng, xám nhạt đều màu được đưa về trắng; nền phức tạp giữ nguyên. Áp cho ảnh tải lên sau."
      checked={value !== false}
      disabled={user?.role !== "owner" || save.isPending}
      onChange={(v) => save.mutate(v)}
    />
  );
}

/** Ảnh sản phẩm (e6): tải lên → tự xoay, cân sáng, làm sạch nền sáng (tắt được), cắt vuông giữ món ở giữa; sắp thứ
 * tự, đặt ảnh bìa. */
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
  const [picking, setPicking] = useState(false);
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
              overlay={
                img.is_primary || img.source === "supplier" ? (
                  <span className="flex flex-col items-end gap-1">
                    {img.source === "supplier" ? <Badge tone="warning">Ảnh nhà cung cấp</Badge> : null}
                    {img.is_primary ? <Badge tone="accent">Ảnh bìa</Badge> : null}
                  </span>
                ) : null
              }
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
        {product.candidate_id ? (
          <li>
            <button
              type="button"
              onClick={() => setPicking(true)}
              className="grid aspect-square w-full place-items-center rounded-md border border-dashed border-line-strong text-ink-2 hover:border-ink-3 hover:text-ink"
            >
              <span className="flex flex-col items-center gap-1.5 px-2 text-center text-[14px]">
                <Images className="size-6" aria-hidden />
                Lấy từ ảnh nhà cung cấp
              </span>
            </button>
          </li>
        ) : null}
      </ul>
      {picking ? <SupplierImagePicker product={product} onClose={() => setPicking(false)} /> : null}
      <CleanBackgroundSwitch />
      <p className="text-[13px] text-ink-3">
        Chỉ chỉnh ảnh thật: xoay theo EXIF, cân sáng nhẹ, làm trắng nền sáng khi nền đủ đơn giản, cắt vuông giữ món ở giữa, tạo bản webp. Không tách nền bằng AI, không tạo ảnh giả. Hoàn tác từng ảnh trong Nhật ký AI.
      </p>
    </div>
  );
}

/** Chị tích ảnh nhà cung cấp (đã lưu ở hồ sơ ứng viên) để dùng ở website/bài đăng — không có gì tự chép. Ảnh chọn đi
 * đúng đường xử lý như ảnh chị tải lên và được đánh dấu «Ảnh nhà cung cấp» (chỉ ở desk). */
function SupplierImagePicker({ product, onClose }: { product: DeskProduct; onClose: () => void }) {
  const opts = useSupplierImageOptions(product.id, true);
  const [picked, setPicked] = useState<string[]>([]);
  const qc = useQueryClient();
  const add = useProductMutation(product.id, async (urls: string[]) => {
    const out = await deskProductApi.addSupplierImages(product.id, urls);
    await qc.invalidateQueries({ queryKey: ["catalog", "product", product.id, "supplier-images"] });
    return out;
  });
  const toggle = (url: string) => setPicked((p) => (p.includes(url) ? p.filter((u) => u !== url) : [...p, url]));
  const list = opts.data ?? [];
  const usable = list.filter((o) => o.cached && !o.used);

  return (
    <Sheet
      open
      onClose={onClose}
      size="lg"
      dismissOnBackdrop={false}
      title="Lấy từ ảnh nhà cung cấp"
      description="Chị tích những ảnh muốn dùng. Ảnh được xoay, cân sáng, cắt vuông như ảnh chị tải lên; sắp thứ tự và đặt ảnh bìa sau."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          <Button
            disabled={!picked.length}
            loading={add.isPending}
            onClick={() =>
              add.mutate(picked, {
                onSuccess: () => {
                  notifySuccess(`Đã thêm ${picked.length} ảnh nhà cung cấp`);
                  onClose();
                },
                onError: notifyError,
              })
            }
          >
            {picked.length ? `Dùng ${picked.length} ảnh` : "Chọn ảnh"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="rounded-md bg-review-wash px-3 py-2 text-[13px] text-ink-2 [text-wrap:pretty]">
          Ảnh nhà cung cấp có thể có hình mờ (watermark) hoặc thuộc bản quyền của shop; khách thường tin ảnh chị tự chụp hơn.
          Website không ghi tên hay link nhà cung cấp.
        </p>
        {opts.isPending ? (
          <p className="text-[14px] text-ink-2">Đang tải ảnh…</p>
        ) : opts.error ? (
          <p className="text-[14px] text-danger">Chưa tải được: {opts.error.message}</p>
        ) : list.length === 0 ? (
          <p className="text-[14px] text-ink-2">
            Hồ sơ ứng viên chưa có ảnh nhà cung cấp. Chị mở Bàn chọn → món này → «Lấy ảnh và chi tiết».
          </p>
        ) : (
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {list.map((o) => {
              const on = picked.includes(o.source_url);
              const disabled = !o.cached || o.used;
              return (
                <li key={o.source_url}>
                  <button
                    type="button"
                    disabled={disabled}
                    aria-pressed={on}
                    aria-label={o.used ? "Ảnh đã dùng" : o.cached ? "Chọn ảnh này" : "Ảnh chưa lưu về máy"}
                    onClick={() => toggle(o.source_url)}
                    className={cn("relative block w-full rounded-md border-2", on ? "border-accent" : "border-transparent", disabled && "opacity-50")}
                  >
                    <ImageBox src={o.src} alt="" ratio="1/1" placeholder="" referrerPolicy="no-referrer" />
                    {on ? (
                      <span className="absolute top-1 right-1 grid size-6 place-items-center rounded-sm bg-accent text-on-accent">
                        <Check className="size-4" aria-hidden />
                      </span>
                    ) : null}
                    {o.used ? <span className="absolute inset-x-1 bottom-1"><Badge tone="neutral">Đã dùng</Badge></span> : null}
                    {!o.cached && !o.used ? <span className="absolute inset-x-1 bottom-1"><Badge tone="outline">Chưa lưu về máy</Badge></span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {list.length > 0 && usable.length < list.filter((o) => !o.used).length ? (
          <p className="text-[12.5px] text-ink-3">Ảnh «chưa lưu về máy» chọn được sau khi chị bấm «Lấy lại ảnh và chi tiết» ở hồ sơ ứng viên.</p>
        ) : null}
      </div>
    </Sheet>
  );
}
