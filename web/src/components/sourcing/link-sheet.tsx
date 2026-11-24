"use client";

import { Link2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Input, Sheet, notifyError } from "@/components/ui";
import { useImportLink, useRun } from "@/lib/api/sourcing";
import { RunProgress } from "./run-progress";

/** a2 — Dán link một sản phẩm bất kỳ: AI lấy giá, ảnh, thông số, đánh giá, dịch sang tiếng Việt. */
export function LinkSheet({ open, onClose, briefId }: { open: boolean; onClose: () => void; briefId?: string }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const importLink = useImportLink();
  const run = useRun(runId);
  const r = run.data;

  useEffect(() => {
    const cid = r?.status === "succeeded" ? r.progress?.candidate_ids?.[0] : undefined;
    if (cid) router.push(`/desk/san-hang/ung-vien/${cid}?tham-dinh=1`);
  }, [r, router]);

  const valid = /^https?:\/\/\S+\.\S+/.test(url.trim());

  function close() {
    setRunId(null);
    setUrl("");
    onClose();
  }

  return (
    <Sheet
      open={open}
      onClose={close}
      title="Dán link sản phẩm"
      description="Link 1688, Taobao, Rakuten, Amazon Nhật hoặc trang bất kỳ. AI đọc trang và dịch sang tiếng Việt."
      footer={
        <Button
          block
          icon={<Link2 className="size-4" />}
          disabled={!valid || !!runId}
          loading={importLink.isPending}
          onClick={() =>
            importLink.mutate(
              { url: url.trim(), brief_id: briefId },
              { onSuccess: (res) => setRunId(res.id), onError: notifyError },
            )
          }
        >
          Lấy hồ sơ
        </Button>
      }
    >
      <Input
        label="Link"
        type="url"
        inputMode="url"
        placeholder="https://item.taobao.com/item.htm?id=…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        error={url && !valid ? "Link chưa đúng, cần bắt đầu bằng https://" : undefined}
        autoFocus
      />
      {r ? <div className="mt-4">{<RunProgress run={r} />}</div> : null}
    </Sheet>
  );
}
