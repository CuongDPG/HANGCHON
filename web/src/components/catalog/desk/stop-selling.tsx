"use client";

import { Ban, CircleAlert, ExternalLink, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, SectionLabel } from "@/components/ui/card";
import { Checkbox, Switch } from "@/components/ui/choice";
import { useConfirm } from "@/components/ui/confirm";
import { DateTime, useNow } from "@/components/ui/date-time";
import { SkeletonList } from "@/components/ui/feedback";
import { Input } from "@/components/ui/field";
import { Sheet } from "@/components/ui/overlay";
import { Segmented } from "@/components/ui/segmented";
import { notifySuccess } from "@/components/ui/toast";
import {
  useResumeSelling,
  type OverdueAction,
  useStopPlan,
  useStopSelling,
  type DeskProduct,
  type StopPlan,
  type StopPostRow,
  type StopStep,
  type StopStepStatus,
} from "@/lib/api/catalog";

const STEP_TONE: Record<StopStepStatus, { label: string; tone: BadgeTone }> = {
  done: { label: "Xong", tone: "success" },
  needs_manual: { label: "Chị xem", tone: "warning" },
  failed: { label: "Lỗi", tone: "danger" },
  skipped: { label: "Giữ lại", tone: "neutral" },
  info: { label: "Lưu ý", tone: "outline" },
};

function PostLink({ url }: { url: string | null }) {
  if (!url) return null;
  if (url.startsWith("/"))
    return (
      <Link href={url} className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent">
        Mở xưởng nội dung
      </Link>
    );
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent">
      Mở bài <ExternalLink className="size-3.5" aria-hidden />
    </a>
  );
}

/** Kết quả từng bước sau khi ngừng bán / mở bán lại. */
export function StopSteps({ steps }: { steps: StopStep[] }) {
  return (
    <ul className="flex flex-col divide-y divide-line">
      {steps.map((s, i) => (
        <li key={`${s.kind}-${s.id ?? i}`} className="flex items-start gap-3 py-2.5">
          <Badge tone={STEP_TONE[s.status].tone} className="mt-0.5 shrink-0">
            {STEP_TONE[s.status].label}
          </Badge>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold">{s.label}</p>
            <p className="text-[14px] text-ink-2">{s.detail}</p>
            {s.kind === "drop" && s.id ? (
              <Link href={`/desk/san-pham/dot/${s.id}`} className="text-[13px] font-semibold text-accent">
                Mở đợt
              </Link>
            ) : (
              <PostLink url={s.url} />
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

type PostMode = "hide" | "delete" | "manual";
function postMode(p: StopPostRow, deleteAll: boolean): PostMode {
  if (p.status === "draft_pushed") return "manual";
  if (deleteAll && p.can_delete) return "delete";
  if (p.can_hide) return "hide";
  return "manual";
}
const MODE_TEXT: Record<PostMode, string> = {
  hide: "Ẩn bài, hiện lại khi mở bán lại",
  delete: "Xoá hẳn, không khôi phục được",
  manual: "Cần gỡ tay",
};

function StopForm({ plan, onDone }: { plan: StopPlan; onDone: (steps: StopStep[]) => void; }) {
  const stop = useStopSelling(plan.product_id);
  const [off, setOff] = useState<Set<string>>(new Set()); // mục chị bỏ tích
  const [manual, setManual] = useState<Set<string>>(new Set()); // bài gỡ tay chị đã gỡ
  const [deleteAll, setDeleteAll] = useState(false);
  const on = (id: string) => !off.has(id);
  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
    const n = new Set(set);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setter(n);
  };
  const anyDelete = plan.posts.some((p) => p.can_delete);

  const submit = () =>
    stop.mutate(
      {
        cancel_post_ids: plan.scheduled_posts.filter((p) => on(p.id)).map((p) => p.id),
        remove_posts: plan.posts.filter((p) => on(p.id)).map((p) => ({ id: p.id, manual_done: manual.has(p.id) })),
        listing_ids: plan.listings.filter((l) => on(l.id)).map((l) => l.id),
        delete_posts: deleteAll,
      },
      { onSuccess: (run) => { notifySuccess("Đã ngừng bán"); onDone(run.steps); } },
    );

  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-1">
        <SectionLabel>Website</SectionLabel>
        <Checkbox checked disabled readOnly label="Gỡ khỏi kệ website" description={plan.website_published ? "Đang trên kệ" : "Đang tạm ẩn"} />
      </section>

      {plan.scheduled_posts.length ? (
        <section className="flex flex-col gap-1">
          <SectionLabel>Lịch đăng chưa đăng</SectionLabel>
          {plan.scheduled_posts.map((p) =>
            p.status === "planned" ? (
              <Checkbox key={p.id} checked disabled readOnly label={`Huỷ bài chờ duyệt ${p.label}`} description="Chưa duyệt" />
            ) : (
              <Checkbox
                key={p.id}
                checked={on(p.id)}
                onChange={() => toggle(off, setOff, p.id)}
                label={`Huỷ lịch ${p.label}`}
                description={p.scheduled_at ? <>hẹn <DateTime value={p.scheduled_at} format="dateTime" /></> : undefined}
              />
            ),
          )}
        </section>
      ) : null}

      {plan.posts.length ? (
        <section className="flex flex-col gap-1">
          <SectionLabel>Bài đã đăng</SectionLabel>
          {anyDelete ? (
            <div className="mb-1 rounded-md bg-seal-wash px-3 py-2">
              <Switch
                checked={deleteAll}
                onChange={setDeleteAll}
                label="Xoá hẳn bài đã đăng"
                description="Không khôi phục được. Facebook, Instagram, Threads xoá hẳn; mở bán lại không có lại bài."
              />
            </div>
          ) : null}
          {plan.posts.map((p) => {
            const mode = postMode(p, deleteAll);
            return (
              <div key={p.id} className="flex flex-col gap-0.5">
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <Checkbox
                      checked={on(p.id)}
                      onChange={() => toggle(off, setOff, p.id)}
                      label={
                        <span className="inline-flex flex-wrap items-center gap-1.5">
                          {p.label}
                          {p.status === "draft_pushed" ? <Badge tone="outline">nháp trong app</Badge> : null}
                          {p.simulated ? <Badge tone="outline">giả lập</Badge> : null}
                        </span>
                      }
                      description={mode === "manual" && p.can_delete ? "Không ẩn được: cần gỡ tay, hoặc bật «Xoá hẳn»" : MODE_TEXT[mode]}
                    />
                  </div>
                  <span className="pt-1.5"><PostLink url={p.url} /></span>
                </div>
                {mode === "manual" && on(p.id) ? (
                  <div className="pl-8">
                    <Checkbox checked={manual.has(p.id)} onChange={() => toggle(manual, setManual, p.id)} label="Đã gỡ tay" />
                  </div>
                ) : null}
              </div>
            );
          })}
        </section>
      ) : null}

      {plan.listings.length ? (
        <section className="flex flex-col gap-1">
          <SectionLabel>Sàn</SectionLabel>
          {plan.listings.map((l) => (
            <Checkbox
              key={l.id}
              checked={on(l.id)}
              onChange={() => toggle(off, setOff, l.id)}
              label={
                <span className="inline-flex items-center gap-1.5">
                  {l.label}
                  {l.simulated ? <Badge tone="outline">giả lập</Badge> : null}
                </span>
              }
              description={l.auto ? "Ngừng bán trên sàn, mở bán lại được" : "Sàn chưa có lệnh ngừng bán qua API: đặt tồn về 0"}
            />
          ))}
        </section>
      ) : null}

      {plan.drops.length ? (
        <Card tone="danger" className="flex flex-col gap-1.5">
          <p className="flex items-center gap-1.5 font-semibold">
            <CircleAlert className="size-4 text-seal" aria-hidden /> Đợt đang mở có món này — không tự đóng
          </p>
          <ul className="flex flex-col gap-1 text-[14px]">
            {plan.drops.map((d) => (
              <li key={d.id}>
                <Link href={`/desk/san-pham/dot/${d.id}`} className="font-semibold text-accent">
                  Đợt {d.code}: {d.title}
                </Link>{" "}
                <span className="text-ink-2">
                  · {d.status_label}
                  {d.slots_reserved ? ` · ${d.slots_reserved} suất đã đặt` : ""}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-[13.5px] text-ink-2">Món ẩn khỏi trang đợt, khách không đặt thêm; đơn đã đặt vẫn giữ. Đóng đợt hay không là chị quyết.</p>
        </Card>
      ) : null}

      <div className="sticky bottom-0 -mb-1 flex flex-wrap gap-2 bg-surface py-2">
        <Button variant="danger" icon={<Ban className="size-4" />} loading={stop.isPending} onClick={submit}>
          Ngừng bán{deleteAll ? " và xoá hẳn bài" : ""}
        </Button>
      </div>
    </div>
  );
}

function resumeMessage(plan: StopPlan | undefined): string {
  const last = plan?.last_stop;
  const parts = [
    "Website lên lại như trước khi ngừng bán",
    last?.hidden_posts ? `hiện lại ${last.hidden_posts} bài đã ẩn` : null,
    last?.listings ? `mở bán lại trên ${last.listings} sàn` : null,
  ].filter(Boolean);
  const gone = (last?.gone_posts ?? 0) + (last?.cancelled_posts ?? 0);
  return `${parts.join(", ")}.${gone ? ` ${gone} bài/lịch đăng đã gỡ hoặc huỷ không tự quay lại.` : ""}`;
}

const OVERDUE_OPTIONS: { value: OverdueAction; label: string }[] = [
  { value: "now", label: "Đăng ngay" },
  { value: "reschedule", label: "Hẹn lại giờ" },
  { value: "drop", label: "Bỏ" },
];
type OverduePick = { action: OverdueAction | ""; at: string };

/** Mở bán lại khi có bài chị giữ lại đã quá giờ hẹn: chị chọn từng bài (hoặc cả loạt) trước, không tự đăng. */
function ResumeForm({ plan, onDone }: { plan: StopPlan; onDone: (steps: StopStep[]) => void }) {
  const resume = useResumeSelling(plan.product_id);
  const [picks, setPicks] = useState<Record<string, OverduePick>>({});
  const pick = (id: string) => picks[id] ?? { action: "", at: "" };
  const set = (id: string, v: Partial<OverduePick>) => setPicks((s) => ({ ...s, [id]: { ...pick(id), ...v } }));
  const actions = plan.overdue_posts.map((p) => pick(p.id).action);
  const all = actions.every((a) => a === actions[0]) ? actions[0] : "";
  const setAll = (action: OverdueAction) =>
    setPicks((s) => Object.fromEntries(plan.overdue_posts.map((p) => [p.id, { ...(s[p.id] ?? { at: "" }), action }])));
  const now = useNow();
  const ready = plan.overdue_posts.every((p) => {
    const c = pick(p.id);
    return c.action === "reschedule" ? Boolean(c.at) && new Date(c.at).getTime() > (now ?? 0) : c.action !== "";
  });

  const submit = () =>
    resume.mutate(
      {
        overdue: plan.overdue_posts.map((p) => {
          const c = pick(p.id);
          return { id: p.id, action: c.action as OverdueAction, scheduled_at: c.action === "reschedule" ? new Date(c.at).toISOString() : null };
        }),
      },
      { onSuccess: (run) => { notifySuccess("Đã mở bán lại"); onDone(run.steps); } },
    );

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[14px] text-ink-2">{resumeMessage(plan)}</p>
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionLabel>Bài đã quá giờ hẹn</SectionLabel>
          {plan.overdue_posts.length > 1 ? (
            <Segmented<OverdueAction | ""> size="sm" aria-label="Chọn cho tất cả" value={all} onChange={(v) => v && setAll(v)} options={OVERDUE_OPTIONS} />
          ) : null}
        </div>
        <ul className="flex flex-col divide-y divide-line">
          {plan.overdue_posts.map((p) => {
            const c = pick(p.id);
            return (
              <li key={p.id} className="flex flex-col gap-2 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[15px] font-semibold">{p.label}</p>
                    {p.scheduled_at ? (
                      <p className="text-[14px] text-ink-2">
                        hẹn <DateTime value={p.scheduled_at} format="dateTime" />
                      </p>
                    ) : null}
                  </div>
                  <Segmented<OverdueAction | ""> size="sm" aria-label={`Bài ${p.label}`} value={c.action} onChange={(v) => v && set(p.id, { action: v })} options={OVERDUE_OPTIONS} />
                </div>
                {c.action === "reschedule" ? (
                  <Input label="Giờ đăng mới" type="datetime-local" value={c.at} onChange={(e) => set(p.id, { at: e.target.value })} />
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>
      <div className="sticky bottom-0 -mb-1 flex flex-wrap gap-2 bg-surface py-2">
        <Button icon={<RotateCcw className="size-4" />} loading={resume.isPending} disabled={!ready} onClick={submit}>
          Mở bán lại
        </Button>
      </div>
    </div>
  );
}

/**
 * «Ngừng bán» (món đang bán / tạm ẩn) hoặc «Mở bán lại» (món đã ngừng bán) — một chỗ vào duy nhất, dùng ở đầu trang
 * sản phẩm và tab Website của xưởng nội dung. Chỉ chị (owner) thấy nút.
 */
export function StopSellingButton({ product, size = "md" }: { product: DeskProduct; size?: "sm" | "md" }) {
  const [open, setOpen] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [steps, setSteps] = useState<StopStep[] | null>(null);
  const stopped = product.status === "stopped";
  const selling = product.status === "published" || product.status === "paused";
  const plan = useStopPlan(product.id, open || stopped);
  const resume = useResumeSelling(product.id);
  const confirm = useConfirm();
  if (!stopped && !selling) return null;

  const close = () => { setOpen(false); setResuming(false); setSteps(null); };
  const doResume = async () => {
    if (plan.data?.overdue_posts.length) {
      setResuming(true);
      setOpen(true);
      return;
    }
    const ok = await confirm({ title: "Mở bán lại món này?", message: resumeMessage(plan.data), confirmLabel: "Mở bán lại" });
    if (!ok) return;
    resume.mutate(undefined, {
      onSuccess: (run) => { notifySuccess("Đã mở bán lại"); setSteps(run.steps); setOpen(true); },
    });
  };

  return (
    <>
      {stopped ? (
        <Button size={size} variant="secondary" icon={<RotateCcw className="size-4" />} loading={resume.isPending} onClick={doResume}>
          Mở bán lại
        </Button>
      ) : (
        <Button size={size} variant="secondary" icon={<Ban className="size-4" />} onClick={() => setOpen(true)}>
          Ngừng bán
        </Button>
      )}
      <Sheet
        open={open}
        onClose={close}
        dismissOnBackdrop={false}
        size="lg"
        title={steps ? `Kết quả: ${product.name}` : resuming ? `Mở bán lại «${product.name}»` : `Ngừng bán «${product.name}» trên mọi kênh`}
        footer={steps ? <Button variant="secondary" onClick={close}>Đóng</Button> : undefined}
      >
        {steps ? (
          <StopSteps steps={steps} />
        ) : resuming && plan.data ? (
          <ResumeForm plan={plan.data} onDone={setSteps} />
        ) : plan.isPending ? (
          <SkeletonList rows={4} />
        ) : plan.data && plan.data.can_stop ? (
          <StopForm plan={plan.data} onDone={setSteps} />
        ) : (
          <p className="text-[14px] text-ink-2">{plan.error?.message ?? "Món này không ở trạng thái đang bán."}</p>
        )}
      </Sheet>
    </>
  );
}

/** Trang sản phẩm khi món đã ngừng bán: các bước còn cần chị xem (gỡ tay, lỗi, đợt đang mở) của lần ngừng gần nhất. */
export function StopFollowUp({ productId }: { productId: string }) {
  const plan = useStopPlan(productId, true);
  const last = plan.data?.last_stop;
  const todo = (last?.steps ?? []).filter((s) => s.status === "needs_manual" || s.status === "failed");
  if (!last || last.undone_at || !todo.length) return null;
  return (
    <Card tone="danger" className="flex flex-col gap-1">
      <p className="flex items-center gap-1.5 font-semibold">
        <CircleAlert className="size-4 text-seal" aria-hidden /> Ngừng bán <DateTime value={last.at} format="dateTime" /> · {todo.length} việc chị xem
      </p>
      <StopSteps steps={todo} />
    </Card>
  );
}
