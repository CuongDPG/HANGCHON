"use client";

import { BellRing, Check } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Sheet } from "@/components/ui/overlay";
import { notifyError } from "@/components/ui/toast";
import { catalogApi } from "@/lib/api/catalog";

/** «Nhắc mình» ở đợt sắp mở: lưu số điện thoại / Zalo, đợt mở thì chị nhắn một lần. */
export function RemindButton({ slug, title }: { slug: string; title: string }) {
  const [open, setOpen] = useState(false);
  const [contact, setContact] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await catalogApi.remind(slug, contact.trim());
      setDone(true);
      setOpen(false);
    } catch (err) {
      notifyError(err);
    } finally {
      setSaving(false);
    }
  }

  if (done) {
    return (
      <span className="inline-flex items-center gap-1 text-[14px] font-medium text-auto">
        <Check className="size-4" aria-hidden /> Sẽ nhắc bạn
      </span>
    );
  }
  return (
    <>
      <Button variant="secondary" size="sm" icon={<BellRing className="size-4" />} onClick={() => setOpen(true)}>
        Nhắc mình
      </Button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Nhắc mình khi đợt mở"
        footer={
          <Button type="submit" form={`remind-${slug}`} block loading={saving} disabled={contact.trim().length < 6}>
            Nhắc mình
          </Button>
        }
      >
        <form id={`remind-${slug}`} onSubmit={submit} className="flex flex-col gap-3">
          <p className="text-[15px] text-ink-2">
            «{title}» mở là chị nhắn bạn đúng một tin. Không nhắn quảng cáo khác.
          </p>
          <Input
            label="Số điện thoại hoặc Zalo"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            inputMode="tel"
            autoComplete="tel"
            required
            maxLength={200}
          />
        </form>
      </Sheet>
    </>
  );
}
