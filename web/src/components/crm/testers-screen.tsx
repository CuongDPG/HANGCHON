"use client";

import { Copy, FlaskConical, PackageCheck, Star, UserPlus } from "lucide-react";
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  DateTime,
  EmptyState,
  ImageBox,
  PageHeader,
  SectionLabel,
  SkeletonList,
  Textarea,
  notifyError,
  notifySuccess,
} from "@/components/ui";
import { INVITE_STATUS_LABEL, useInviteStatus, useInviteTesters, useTrialCandidates, type TesterInvite, type TrialCandidate } from "@/lib/api/crm";
import { CustomerPicker } from "./customer-picker";
import { KhachNav } from "./khach-nav";

/** Khách thử hàng cùng chị (h8): mời khách quen dùng thử món đang ở cột «Đang thử»; nhận xét hiện cạnh ghi chú thử. */
export function TestersScreen() {
  const { data, isPending, error, refetch } = useTrialCandidates();
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Khách thử hàng" />
      <KhachNav active="testers" />
      {isPending ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được món đang thử"
          description={error.message}
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : data.length === 0 ? (
        <EmptyState
          icon={<FlaskConical />}
          title="Chưa có món nào đang thử"
          description="Chuyển một ứng viên sang cột «Đang thử» ở Bàn chọn, rồi quay lại đây để mời khách thử cùng."
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {data.map((c) => (
            <li key={c.id}>
              <CandidateCard c={c} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CandidateCard({ c }: { c: TrialCandidate }) {
  const invite = useInviteTesters();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <ImageBox src={c.image_url} alt={c.title} ratio="1/1" className="w-16 shrink-0" placeholder="Ảnh" />
        <div className="min-w-0 flex-1">
          <h2 className="text-[17px] leading-snug font-semibold [text-wrap:pretty]">{c.title}</h2>
          <p className="text-[13px] text-ink-2">
            {c.stage_changed_at ? (
              <>
                Đang thử từ <DateTime value={c.stage_changed_at} format="date" />
              </>
            ) : (
              "Đang thử"
            )}{" "}
            · {c.invites.length} khách thử cùng
          </p>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="flex flex-col gap-2">
          <SectionLabel>Ghi chú thử của chị</SectionLabel>
          {c.notes.length === 0 ? (
            <p className="text-[14px] text-ink-2">Chưa có ghi chú thử.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {c.notes.map((n) => (
                <li key={n.id} className="rounded-md bg-soft px-3 py-2">
                  <p className="text-[12.5px] text-ink-2">{n.trial_day ? `Ngày ${n.trial_day}` : <DateTime value={n.recorded_at} format="date" />}</p>
                  <p className="text-[14.5px] [text-wrap:pretty]">{n.text ?? "(ghi âm / ảnh)"}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="flex flex-col gap-2">
          <SectionLabel>Khách thử</SectionLabel>
          {c.invites.length === 0 ? <p className="text-[14px] text-ink-2">Chưa mời ai.</p> : null}
          <ul className="flex flex-col gap-2">
            {c.invites.map((i) => (
              <li key={i.id}>
                <InviteRow i={i} />
              </li>
            ))}
          </ul>
          <Button size="sm" variant="secondary" icon={<UserPlus className="size-4" />} className="self-start" onClick={() => setOpen(true)}>
            Mời khách thử
          </Button>
        </section>
      </div>
      <CustomerPicker
        open={open}
        onClose={() => setOpen(false)}
        title={`Mời thử: ${c.title}`}
        description="Mỗi khách nhận một đường link riêng để trả lời và gửi cảm nhận một lần."
        multiple
        segment="regular"
        confirmLabel="Gửi lời mời"
        loading={invite.isPending}
        onPick={async (picked) => {
          const res = await invite.mutateAsync({ candidateId: c.id, customerIds: picked.map((p) => p.id), message });
          setOpen(false);
          setMessage("");
          const sent = res.filter((r) => r.status === "invited").length;
          notifySuccess(sent === res.length ? `Đã mời ${sent} khách` : `Đã mời ${sent}/${res.length} khách — số còn lại chưa có kênh nhận tin, chị chép link gửi tay`);
        }}
      />
      {open ? null : (
        <details className="text-[13.5px] text-ink-2">
          <summary className="cursor-pointer">Lời mời gửi khách</summary>
          <Textarea
            aria-label="Lời mời"
            className="mt-2"
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Để trống: «Chào {tên}, mình đang thử {món} trước khi quyết định có bán không…»"
          />
        </details>
      )}
    </Card>
  );
}

function InviteRow({ i }: { i: TesterInvite }) {
  const status = useInviteStatus();
  async function copy() {
    try {
      await navigator.clipboard.writeText(i.link);
      notifySuccess("Đã chép link");
    } catch {
      notifyError("Trình duyệt không cho chép link.");
    }
  }
  return (
    <div className="rounded-md border border-line px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[14.5px] font-medium">{i.customer_name}</span>
        <Badge tone={i.status === "feedback_received" ? "success" : i.status === "declined" ? "danger" : "neutral"} className="shrink-0">
          {INVITE_STATUS_LABEL[i.status]}
        </Badge>
      </div>
      {i.feedback ? (
        <blockquote className="mt-1.5 border-l-2 border-accent pl-2.5 text-[14.5px] [text-wrap:pretty]">
          {i.feedback_rating ? (
            <span className="mb-0.5 flex items-center gap-0.5 text-review" aria-label={`${i.feedback_rating} trên 5 sao`}>
              {Array.from({ length: 5 }, (_, k) => (
                <Star key={k} className="size-3.5" aria-hidden fill={k < i.feedback_rating! ? "currentColor" : "none"} />
              ))}
            </span>
          ) : null}
          {i.feedback}
        </blockquote>
      ) : null}
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {i.status === "invited" || i.status === "accepted" ? (
          <Button size="sm" variant="ghost" icon={<PackageCheck className="size-4" />} loading={status.isPending} onClick={() => status.mutate({ id: i.id, status: "sample_sent" })}>
            Đã gửi mẫu
          </Button>
        ) : null}
        {i.status === "draft" ? (
          <Button size="sm" variant="ghost" loading={status.isPending} onClick={() => status.mutate({ id: i.id, status: "invited" })}>
            Đã gửi link tay
          </Button>
        ) : null}
        {i.status !== "feedback_received" && i.status !== "closed" ? (
          <Button size="sm" variant="ghost" icon={<Copy className="size-4" />} onClick={copy}>
            Chép link
          </Button>
        ) : null}
      </div>
    </div>
  );
}
