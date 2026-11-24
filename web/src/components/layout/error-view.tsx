"use client";

import { RotateCw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/feedback";
import { errorMessage } from "@/lib/api/client";

/** Nội dung chung cho các file error.tsx: báo lỗi tiếng Việt + nút thử lại. */
export function ErrorView({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <EmptyState
      tone="error"
      icon={<TriangleAlert />}
      title="Trang này đang gặp lỗi"
      description={errorMessage(error)}
      action={
        <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => retry()}>
          Thử lại
        </Button>
      }
      className="mt-4"
    />
  );
}
