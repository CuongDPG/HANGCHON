"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Camera, X } from "lucide-react";
import { useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Button, IconButton, InlineSelect, Input, Sheet, notifySuccess } from "@/components/ui";
import { EXPENSE_CATEGORY_LABELS, useCreateExpense, type ExpenseCategory } from "@/lib/api/finance";
import { formatNumber } from "@/lib/format";

const schema = z.object({
  incurred_on: z.string().min(1, "Chọn ngày chi"),
  category: z.string().min(1),
  amount: z.string().refine((v) => Number(v.replace(/\D/g, "")) > 0, "Nhập số tiền lớn hơn 0"),
  description: z.string().trim().min(1, "Ghi vài chữ: chi cho việc gì").max(2000),
  vendor: z.string().max(200).optional(),
});
type Values = z.infer<typeof schema>;

function todayVN(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
}

/** Nhập chi phí tay kèm ảnh chứng từ (k1). */
export function ExpenseSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateExpense();
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { register, handleSubmit, control, reset, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { incurred_on: todayVN(), category: "packaging", amount: "", description: "", vendor: "" },
  });
  const amount = useWatch({ control, name: "amount" });

  function close() {
    reset();
    setFile(null);
    onClose();
  }

  const onSubmit = handleSubmit(async (v) => {
    await create.mutateAsync({
      incurred_on: v.incurred_on,
      category: v.category as ExpenseCategory,
      amount_vnd: Number(v.amount.replace(/\D/g, "")),
      description: v.description.trim(),
      vendor: v.vendor?.trim() || undefined,
      receipt: file,
    });
    notifySuccess("Đã ghi khoản chi vào sổ");
    close();
  });

  return (
    <Sheet
      open={open}
      onClose={close}
      title="Ghi khoản chi"
      description="Ghi xong là vào sổ ngay. Chụp kèm hoá đơn, biên lai để khai thuế."
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Huỷ
          </Button>
          <Button type="submit" form="expense-form" loading={create.isPending}>
            Ghi vào sổ
          </Button>
        </>
      }
    >
      <form id="expense-form" onSubmit={onSubmit} className="flex flex-col gap-3">
        <Input
          label="Số tiền"
          inputMode="numeric"
          trailing="đ"
          error={formState.errors.amount?.message}
          {...register("amount")}
          value={amount ? formatNumber(Number(amount.replace(/\D/g, "")) || 0) : ""}
        />
        <Input label="Chi cho việc gì" placeholder="Vd: hộp giấy carton 200 cái" error={formState.errors.description?.message} {...register("description")} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Ngày chi" type="date" error={formState.errors.incurred_on?.message} {...register("incurred_on")} />
          <Controller
            control={control}
            name="category"
            render={({ field }) => (
              <InlineSelect
                label="Nhóm"
                value={field.value}
                onChange={field.onChange}
                options={Object.entries(EXPENSE_CATEGORY_LABELS).map(([value, label]) => ({ value, label }))}
              />
            )}
          />
        </div>
        <Input label="Nơi bán (tuỳ chọn)" placeholder="Tên cửa hàng, nhà cung cấp" {...register("vendor")} />
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Ảnh chứng từ</span>
          <input
            ref={fileRef}
            type="file"
            accept="image/*,application/pdf"
            capture="environment"
            className="sr-only"
            aria-label="Chọn ảnh chứng từ"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <div className="flex items-center gap-2 rounded-md border border-line bg-paper p-2 pl-3 text-[14px]">
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
              <IconButton
                label="Bỏ ảnh"
                icon={<X />}
                size="sm"
                onClick={() => {
                  setFile(null);
                  if (fileRef.current) fileRef.current.value = "";
                }}
              />
            </div>
          ) : (
            <Button variant="secondary" icon={<Camera className="size-4" />} onClick={() => fileRef.current?.click()} className="self-start">
              Chụp hoặc chọn ảnh
            </Button>
          )}
          <p className="text-[13px] text-ink-2">Ảnh JPG, PNG, HEIC hoặc PDF, tối đa 10 MB.</p>
        </div>
      </form>
    </Sheet>
  );
}
