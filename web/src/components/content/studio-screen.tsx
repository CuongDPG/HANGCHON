"use client";

import { CalendarClock, Clapperboard, ExternalLink, Globe, PenLine, RefreshCw, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  Chip,
  DataList,
  Dialog,
  EmptyState,
  ImageBox,
  Input,
  LevelTag,
  Money,
  PageHeader,
  SectionLabel,
  Sheet,
  SkeletonList,
  Tabs,
  Textarea,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { PageContentEditor } from "@/components/catalog/desk/page-content-editor";
import {
  useApproveDraft,
  useCompose,
  useEditDraft,
  useOverrideCheck,
  useRewriteDraft,
  useStudioDetail,
  type CheckFinding,
  type ContentChannel,
  type Draft,
  type RewritePreset,
  type Scene,
  type StudioDetail,
} from "@/lib/api/content";
import { formatDateTime, formatDayMonth, formatTime, formatWeekday } from "@/lib/format";
import { cn } from "@/lib/cn";
import { CheckChips, ChannelMark, CHANNEL_LABEL, draftDisplay, isDone, localFile, MicButton, StatusBadge, toLocalInput, useSpeech } from "./shared";
import { RelatedLinks } from "@/components/desk/related-links";

const ORDER: ContentChannel[] = ["facebook", "instagram", "threads", "tiktok", "zalo_oa"];
const WEBSITE = "website";

export function StudioScreen({ kind, id }: { kind: "product" | "drop"; id: string }) {
  const { data, isPending, error } = useStudioDetail(kind, id);
  // `?kenh=facebook` (từ Hồ sơ bán của sản phẩm) mở thẳng tab kênh đó
  const initial = useSearchParams().get("kenh");
  const [tab, setTab] = useState<string>(initial ?? "");
  const drafts = useMemo(() => [...(data?.drafts ?? [])].sort((a, b) => ORDER.indexOf(a.channel) - ORDER.indexOf(b.channel)), [data]);
  const done = drafts.filter(isDone).length;
  const isProduct = kind === "product";
  // sản phẩm: Website là kênh đầu tiên (trang chính thức), rồi tới từng mạng xã hội — tab luôn đủ kênh
  const channels: string[] = isProduct ? [WEBSITE, ...ORDER] : drafts.map((d) => d.channel);
  const active = channels.includes(tab) ? tab : (channels[0] ?? "");
  const current = drafts.find((d) => d.channel === active);
  const live = data?.page_status === "published";

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        backHref="/desk/noi-dung"
        eyebrow={kind === "drop" ? "ĐỢT MỞ BÁN" : "XƯỞNG NỘI DUNG"}
        title={data?.name ?? "Xưởng nội dung"}
        actions={data && drafts.length ? <Badge tone={done === drafts.length ? "success" : "neutral"}>{done}/{drafts.length} bài đã duyệt</Badge> : null}
      />
      <RelatedLinks
        links={
          kind === "drop"
            ? [{ href: `/desk/san-pham/dot/${id}`, label: "Đợt mở bán" }]
            : [
                data?.candidate_id && { href: `/desk/ban-chon/${data.candidate_id}`, label: "Hồ sơ chọn (Bàn chọn)" },
                { href: `/desk/san-pham/${id}`, label: "Giá và cách bán (Sản phẩm)" },
              ]
        }
      />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : !data ? null : !isProduct && drafts.length === 0 ? (
        <ComposeEmpty detail={data} />
      ) : (
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_320px] md:items-start">
          <div className="flex min-w-0 flex-col gap-4">
            <Tabs
              aria-label="Kênh"
              value={active}
              onChange={setTab}
              items={channels.map((ch) => {
                if (ch === WEBSITE) return { value: ch, label: `Website${live ? " ✓" : ""}` };
                const d = drafts.find((x) => x.channel === ch);
                return { value: ch, label: `${d?.channel_label ?? CHANNEL_LABEL[ch as ContentChannel] ?? ch}${d && isDone(d) ? " ✓" : ""}` };
              })}
            />
            {active === WEBSITE ? (
              <PageContentEditor productId={id} />
            ) : current ? (
              <DraftPanel key={current.id} draft={current} detail={data} />
            ) : live || !isProduct ? (
              <ComposeEmpty detail={data} />
            ) : (
              <EmptyState
                icon={<Globe />}
                title="Đăng trang website trước, AI sẽ soạn bài các kênh từ trang đó"
                description="Bài Facebook, Instagram, Threads, TikTok và Zalo đều dẫn khách về trang sản phẩm, nên AI chỉ soạn khi trang đã lên website."
                action={
                  <Button variant="secondary" onClick={() => setTab(WEBSITE)}>
                    Mở tab Website
                  </Button>
                }
              />
            )}
          </div>
          <ProfileCard detail={data} />
        </div>
      )}
    </div>
  );
}

function ComposeEmpty({ detail }: { detail: StudioDetail }) {
  const compose = useCompose(detail.kind, detail.id);
  return (
    <EmptyState
      icon={<Sparkles />}
      title="Chưa có bài cho món này"
      description="AI soạn một bản cho mỗi kênh từ hồ sơ chọn, lý do chọn và điều chưa ưng, theo giọng của chị."
      action={
        <Button loading={compose.isPending} onClick={() => compose.mutate({}, { onSuccess: () => notifySuccess("AI đã soạn xong, chị xem từng kênh nhé") })}>
          Soạn bài cho các kênh
        </Button>
      }
    />
  );
}

function ProfileCard({ detail }: { detail: StudioDetail }) {
  const confirm = useConfirm();
  const compose = useCompose(detail.kind, detail.id);
  return (
    <Card tone="soft" className="flex flex-col gap-3 md:sticky md:top-4">
      <SectionLabel>HỒ SƠ ĐỂ AI VIẾT</SectionLabel>
      <DataList
        items={[
          ...(detail.price_vnd ? [{ label: "Giá bán", value: <Money value={detail.price_vnd} /> }] : []),
          ...(detail.trial_days ? [{ label: "Đã thử", value: `${detail.trial_days} ngày` }] : []),
          ...(detail.considered_count ? [{ label: "Đã cân nhắc", value: `${detail.considered_count} món` }] : []),
          ...(detail.drop ? [{ label: "Đợt", value: `${detail.drop.title}${detail.drop.closes_at ? ` · tới ${formatDayMonth(detail.drop.closes_at)}` : ""}` }] : []),
        ]}
      />
      {detail.reason_selected ? (
        <p className="text-[14px]">
          <span className="font-semibold">Lý do chọn: </span>
          {detail.reason_selected}
        </p>
      ) : null}
      {detail.not_satisfied ? (
        <p className="text-[14px]">
          <span className="font-semibold">Chưa ưng: </span>
          {detail.not_satisfied}
        </p>
      ) : null}
      {detail.kind === "drop" || detail.page_status === "published" ? (
        <div className="flex flex-wrap gap-2">
          <a href={detail.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] text-accent">
            Xem trên web <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
      ) : null}
      {detail.drafts.length ? (
      <Button
        variant="ghost"
        size="sm"
        icon={<RefreshCw className="size-4" aria-hidden />}
        loading={compose.isPending}
        onClick={async () => {
          const ok = await confirm({
            title: "Soạn lại tất cả các kênh?",
            message: "AI soạn bản mới cho mọi kênh chưa đăng. Bản đang chờ duyệt sẽ được thay.",
            confirmLabel: "Soạn lại",
          });
          if (ok) compose.mutate({}, { onSuccess: () => notifySuccess("Đã soạn lại") });
        }}
      >
        Soạn lại tất cả
      </Button>
      ) : null}
    </Card>
  );
}

function DraftPanel({ draft, detail }: { draft: Draft; detail: StudioDetail }) {
  const { user: session } = useSession();
  const isOwner = session?.role === "owner";
  const [editing, setEditing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [override, setOverride] = useState<CheckFinding | null>(null);
  const status = draftDisplay(draft);
  const locked = status === "published" || status === "draft_pushed" || status === "drafting";
  const failing = draft.check_findings.filter((f) => !f.ok && !f.overridden);

  if (status === "drafting") {
    return (
      <Card className="flex flex-col gap-3">
        <LevelTag level="review">AI đang soạn</LevelTag>
        <SkeletonList rows={3} />
        <p className="text-[14px] text-ink-2">Bản {draft.channel_label} đang được soạn từ hồ sơ món, trang sẽ tự cập nhật.</p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ChannelMark channel={draft.channel} />
          <span className="font-semibold">{draft.title || draft.channel_label}</span>
          <span className="flex-1" />
          {status !== "pending" ? <StatusBadge status={status} /> : <LevelTag level="review" size="sm">Chờ chị duyệt</LevelTag>}
        </div>
        <Preview draft={draft} detail={detail} />
        <ScheduleLine draft={draft} />
      </Card>

      <div className="flex flex-col gap-2">
        <SectionLabel>SOÁT LỜI TRƯỚC KHI TỚI TAY CHỊ</SectionLabel>
        <CheckChips findings={draft.check_findings} onOverride={isOwner && !locked ? setOverride : undefined} />
        {failing.length ? (
          <Card tone="danger" className="flex flex-col gap-2 text-[14px]">
            {failing.map((f) => (
              <div key={f.key} className="flex flex-col gap-1">
                <p>
                  <span className="font-semibold">{f.label}: </span>
                  {f.detail}
                </p>
                {f.suggestion ? <p className="text-ink-2">Gợi ý: {f.suggestion}</p> : null}
                {isOwner ? (
                  <button type="button" className="self-start text-[13px] font-medium text-seal underline" onClick={() => setOverride(f)}>
                    Vẫn giữ, bỏ qua có lý do
                  </button>
                ) : null}
              </div>
            ))}
          </Card>
        ) : null}
        {draft.feedback_note ? <p className="text-[13px] text-ink-2">Lời nhắn lần trước của chị: «{draft.feedback_note}»</p> : null}
      </div>

      {!locked ? <RewriteBar draft={draft} /> : null}

      {draft.channel === "tiktok" ? <TikTokNote draft={draft} /> : null}

      {!locked ? (
        <div className="flex gap-2">
          <Button variant="secondary" icon={<PenLine className="size-4" aria-hidden />} onClick={() => setEditing(true)} className="flex-1 md:flex-none">
            Sửa tay
          </Button>
          {isOwner ? (
            status === "approved" ? (
              <Button variant="secondary" icon={<CalendarClock className="size-4" aria-hidden />} onClick={() => setApproving(true)} className="flex-1 md:flex-none">
                Đổi giờ đăng
              </Button>
            ) : (
              <Button disabled={!draft.can_approve} onClick={() => setApproving(true)} className="flex-1 md:flex-none">
                Duyệt, xếp lịch
              </Button>
            )
          ) : (
            <p className="flex-1 self-center text-[13px] text-ink-2">Chị là người duyệt bài.</p>
          )}
        </div>
      ) : draft.post?.external_url ? (
        <a href={draft.post.external_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[14px] text-accent">
          Xem bài đã đăng <ExternalLink className="size-3.5" aria-hidden />
        </a>
      ) : null}
      {!draft.can_approve && !locked && isOwner ? (
        <p className="-mt-2 text-[13px] text-seal">Còn mục soát chưa đạt — sửa bài hoặc bỏ qua có lý do thì mới duyệt được.</p>
      ) : null}

      <EditSheet draft={draft} open={editing} onClose={() => setEditing(false)} />
      <ApproveSheet draft={draft} open={approving} onClose={() => setApproving(false)} />
      <OverrideDialog draft={draft} finding={override} onClose={() => setOverride(null)} />
    </div>
  );
}

function Preview({ draft, detail }: { draft: Draft; detail: StudioDetail }) {
  const scenes = draft.script.filter((s): s is Scene => typeof s === "object" && s !== null && "voiceover" in s) as Scene[];
  const img = localFile(detail.image_urls[0] ?? detail.image_url);
  return (
    <div className="flex flex-col gap-3">
      {draft.channel === "instagram" && draft.slides.length ? (
        <div className="-mx-4 flex snap-x gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:px-0" aria-label="Thứ tự ảnh">
          {draft.slides.map((s, i) => (
            <figure key={i} className="w-40 shrink-0 snap-start">
              <ImageBox src={localFile(s.image_url)} alt={s.caption} ratio="4/5" placeholder={`Ảnh ${i + 1}`} />
              <figcaption className="mt-1 text-[12.5px] text-ink-2">
                <span className="font-semibold text-ink">{i + 1}.</span> {s.caption}
              </figcaption>
            </figure>
          ))}
        </div>
      ) : draft.channel === "tiktok" ? (
        draft.video_url ? (
          <video src={localFile(draft.video_url) ?? undefined} controls playsInline className="aspect-[9/16] max-h-[420px] rounded-md bg-ink object-contain" />
        ) : null
      ) : draft.channel === "facebook" || draft.channel === "zalo_oa" ? (
        <ImageBox src={img} alt={detail.name} ratio="16/9" placeholder="Ảnh chị chụp, AI cân sáng" />
      ) : null}

      {draft.channel === "tiktok" && scenes.length ? (
        <ol className="flex flex-col gap-2" aria-label="Kịch bản theo cảnh">
          {scenes.map((s) => (
            <li key={s.scene} className="rounded-md border border-line p-2.5 text-[14px]">
              <div className="flex items-center gap-2 text-[12.5px] text-ink-2">
                <span className="font-semibold text-ink">Cảnh {s.scene}</span>
                <span>· {s.seconds} giây</span>
              </div>
              <p className="mt-1">
                <span className="text-ink-2">Hình: </span>
                {s.visual}
              </p>
              <p>
                <span className="text-ink-2">Lời: </span>«{s.voiceover}»
              </p>
              <p>
                <span className="text-ink-2">Chữ trên hình: </span>
                <span className="font-semibold">{s.on_screen_text}</span>
              </p>
            </li>
          ))}
          <li className="text-[13px] text-ink-2">Tổng {scenes.reduce((a, s) => a + s.seconds, 0)} giây</li>
        </ol>
      ) : null}

      <div className={cn("text-[15px] leading-relaxed whitespace-pre-line", draft.channel === "zalo_oa" && "rounded-md bg-accent-wash p-3")}>
        {draft.body}
      </div>
      {draft.hashtags.length ? <p className="text-[14px] text-accent">{draft.hashtags.join(" ")}</p> : null}
      {draft.link_url ? (
        <p className="text-[13px] text-ink-2">
          {detail.drop ? `${detail.drop.title}${detail.drop.closes_at ? ` mở tới ${formatDayMonth(detail.drop.closes_at)}` : ""} · ` : ""}
          {draft.channel === "instagram" || draft.channel === "tiktok" ? "link ở trang cá nhân" : "link về trang sản phẩm"} · mã bài{" "}
          <span className="font-mono">{draft.src_code}</span>
        </p>
      ) : null}
      {draft.ai_generated ? <p className="text-[12.5px] text-ink-3">Khi đăng sẽ kèm nhãn «Nội dung có sự hỗ trợ của AI».</p> : null}
    </div>
  );
}

function ScheduleLine({ draft }: { draft: Draft }) {
  if (!draft.post) return null;
  const p = draft.post;
  const when = `${formatWeekday(p.scheduled_at)} lúc ${formatTime(p.scheduled_at)}`;
  return (
    <p className="flex items-center gap-1.5 border-t border-line pt-2 text-[13px] text-ink-2">
      <CalendarClock className="size-4 shrink-0" aria-hidden />
      {p.status === "published" ? `Đã đăng ${formatDateTime(p.published_at ?? p.scheduled_at)}` : p.status === "draft_pushed" ? "Đã đẩy bản nháp vào TikTok" : `Dự kiến ${when}`}
      {p.status === "failed" && p.error ? <span className="text-seal"> · lỗi: {p.error}</span> : null}
    </p>
  );
}

const PRESETS: { value: RewritePreset; label: string }[] = [
  { value: "shorter", label: "Ngắn hơn" },
  { value: "warmer", label: "Ấm hơn" },
  { value: "price", label: "Thêm giá" },
];

function RewriteBar({ draft }: { draft: Draft }) {
  const rewrite = useRewriteDraft();
  const [text, setText] = useState("");
  const speech = useSpeech(setText);
  const busy = rewrite.isPending;

  function run(body: { preset?: RewritePreset; instruction?: string }) {
    rewrite.mutate(
      { id: draft.id, ...body },
      {
        onSuccess: (r) => {
          setText("");
          notifySuccess(r.status === "applied" ? "Đã viết lại, chị xem bản mới" : "Bản viết lại đang chờ chị duyệt");
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <SectionLabel>VIẾT LẠI NHANH</SectionLabel>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0">
        {PRESETS.map((p) => (
          <Chip key={p.value} disabled={busy} onClick={() => run({ preset: p.value })}>
            {p.label}
          </Chip>
        ))}
        {speech.supported ? <MicButton listening={speech.listening} disabled={busy} onClick={speech.listening ? speech.stop : speech.start} /> : null}
      </div>
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) run({ instruction: text.trim() });
        }}
      >
        <Input
          aria-label="Ý của chị"
          placeholder="Hoặc gõ ý của chị, vd «nhắc nắp tháo rời»"
          value={text}
          onChange={(e) => setText(e.target.value)}
          wrapperClassName="flex-1"
          hint={speech.error ?? undefined}
        />
        <Button type="submit" variant="secondary" loading={busy} disabled={!text.trim()} icon={<Send className="size-4" aria-hidden />}>
          Viết lại
        </Button>
      </form>
      {busy ? <p className="text-[13px] text-ink-2">AI đang viết lại…</p> : null}
    </div>
  );
}

function TikTokNote({ draft }: { draft: Draft }) {
  return (
    <Card tone="soft" className="flex flex-col gap-2 text-[14px]">
      <p>
        TikTok chỉ cho ứng dụng chưa được duyệt đăng riêng tư, nên hệ thống <b>đẩy bản nháp vào app</b>; chị mở TikTok bấm đăng.
      </p>
      {draft.video ? (
        <p className="text-ink-2">Video kèm theo: {draft.video.duration_seconds ?? "?"} giây, {draft.video.status === "approved" ? "chị đã duyệt" : "chờ chị xem"}.</p>
      ) : (
        <ButtonLink href="/desk/noi-dung/video" variant="secondary" size="sm" icon={<Clapperboard className="size-4" aria-hidden />} className="self-start">
          Dựng video từ clip chị quay
        </ButtonLink>
      )}
    </Card>
  );
}

function EditSheet({ draft, open, onClose }: { draft: Draft; open: boolean; onClose: () => void }) {
  const edit = useEditDraft();
  const [title, setTitle] = useState(draft.title ?? "");
  const [body, setBody] = useState(draft.body);
  const [tags, setTags] = useState(draft.hashtags.join(" "));
  const [script, setScript] = useState(draft.script);
  // mở lại → lấy nội dung mới nhất của bản nháp (điều chỉnh state trong lúc render, không dùng effect)
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setTitle(draft.title ?? "");
      setBody(draft.body);
      setTags(draft.hashtags.join(" "));
      setScript(draft.script);
    }
  }

  function setPart(i: number, key: string, value: string | number) {
    setScript((s) => s.map((x, j) => (j === i ? { ...x, [key]: value } : x)));
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={`Sửa tay bản ${draft.channel_label}`}
      description="Sửa xong, AI soát lại số liệu và lời quảng cáo."
      footer={
        <Button
          block
          loading={edit.isPending}
          onClick={() =>
            edit.mutate(
              { id: draft.id, title, body, hashtags: tags.split(/\s+/).filter(Boolean), script },
              { onSuccess: () => { notifySuccess("Đã lưu và soát lại"); onClose(); } },
            )
          }
        >
          Lưu
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Tên bài (nội bộ)" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Textarea label="Nội dung" rows={10} value={body} onChange={(e) => setBody(e.target.value)} hint={`${body.length} ký tự`} />
        {draft.channel !== "zalo_oa" ? <Input label="Hashtag" value={tags} onChange={(e) => setTags(e.target.value)} hint="Cách nhau bằng dấu cách" /> : null}
        {script.map((s, i) =>
          "voiceover" in s ? (
            <div key={i} className="flex flex-col gap-2 rounded-md border border-line p-2.5">
              <p className="text-[13px] font-semibold">Cảnh {i + 1}</p>
              <Textarea label="Lời thoại" rows={2} value={String(s.voiceover ?? "")} onChange={(e) => setPart(i, "voiceover", e.target.value)} />
              <Input label="Chữ trên hình" value={String(s.on_screen_text ?? "")} onChange={(e) => setPart(i, "on_screen_text", e.target.value)} />
              <Input label="Số giây" type="number" min={1} max={15} value={String(s.seconds ?? 5)} onChange={(e) => setPart(i, "seconds", Number(e.target.value) || 1)} />
            </div>
          ) : "caption" in s ? (
            <Input key={i} label={`Chú thích ảnh ${i + 1}`} value={String(s.caption ?? "")} onChange={(e) => setPart(i, "caption", e.target.value)} />
          ) : null,
        )}
      </div>
    </Sheet>
  );
}

function ApproveSheet({ draft, open, onClose }: { draft: Draft; open: boolean; onClose: () => void }) {
  const approve = useApproveDraft();
  const [at, setAt] = useState(draft.post ? toLocalInput(draft.post.scheduled_at) : "");
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open && draft.post) setAt(toLocalInput(draft.post.scheduled_at));
  }
  const tiktok = draft.channel === "tiktok";
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={tiktok ? "Duyệt, đẩy bản nháp TikTok" : `Duyệt, xếp lịch ${CHANNEL_LABEL[draft.channel]}`}
      description={tiktok ? "Tới giờ, hệ thống đẩy bản nháp vào app TikTok để chị bấm đăng." : "Tới giờ, hệ thống tự đăng. Chị đổi giờ được tới lúc đăng."}
      footer={
        <Button
          block
          loading={approve.isPending}
          disabled={!at}
          onClick={() => {
            const iso = new Date(at).toISOString();
            approve.mutate(
              { id: draft.id, scheduled_at: draft.post && iso === new Date(draft.post.scheduled_at).toISOString() ? null : iso },
              {
                onSuccess: () => {
                  notifySuccess("Đã duyệt, bài nằm trên lịch");
                  onClose();
                },
              },
            );
          }}
        >
          Duyệt, xếp lịch
        </Button>
      }
    >
      <Input label="Đăng lúc" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} hint="Giờ AI chọn theo lúc khách của chị hay xem." />
      <p className="mt-3 text-[13px] text-ink-2">
        <Link href="/desk/noi-dung/lich" className="text-accent">
          Xem cả lịch tuần
        </Link>
      </p>
    </Sheet>
  );
}

function OverrideDialog({ draft, finding, onClose }: { draft: Draft; finding: CheckFinding | null; onClose: () => void }) {
  const ov = useOverrideCheck();
  const [reason, setReason] = useState("");
  const [prev, setPrev] = useState(finding);
  if (finding !== prev) {
    setPrev(finding);
    if (finding) setReason("");
  }
  return (
    <Dialog
      open={!!finding}
      onClose={onClose}
      title={`Bỏ qua «${finding?.label ?? ""}»?`}
      description={finding?.detail}
      footer={
        <div className="flex w-full gap-2">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            Để em sửa
          </Button>
          <Button
            variant="danger"
            className="flex-1"
            loading={ov.isPending}
            disabled={reason.trim().length < 5}
            onClick={() =>
              finding &&
              ov.mutate({ id: draft.id, key: finding.key, reason }, { onSuccess: () => { notifySuccess("Đã ghi lý do bỏ qua"); onClose(); } })
            }
          >
            Bỏ qua, ghi lý do
          </Button>
        </div>
      }
    >
      <Textarea label="Lý do (được lưu vết)" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Vd: đây là lời khách nói, đã xin phép trích" />
    </Dialog>
  );
}
