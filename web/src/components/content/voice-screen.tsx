"use client";

import { Mic, Plus, Sparkles, Square, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, Card, EmptyState, IconButton, Input, PageHeader, SectionLabel, SkeletonList, Textarea, notifySuccess } from "@/components/ui";
import { useSession } from "@/lib/api/auth";
import { useEditVoice, useLearnVoice, useVoice, type Voice, type VoicePatch } from "@/lib/api/content";
import { formatDateTime } from "@/lib/format";
import { ContentNav } from "./shared";
import { useSpeech } from "./use-speech";

/** Giọng của chị (f2): dán bài cũ, nói vài câu (giọng nói → chữ), ghi chú → AI rút hồ sơ giọng; chị xem và sửa. */
export function VoiceScreen() {
  const { data, isPending, error } = useVoice();
  const { user: session } = useSession();
  const owner = session?.role === "owner";
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Giọng của chị" description="Mọi bài AI soạn đều theo hồ sơ này: xưng hô, độ dài câu, từ hay dùng, điều tránh." />
      <ContentNav />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được hồ sơ giọng" description={error.message} />
      ) : data ? (
        <div className="grid gap-4 md:grid-cols-2 md:items-start">
          <Profile voice={data} owner={owner} />
          {owner ? <LearnCard /> : null}
        </div>
      ) : null}
    </div>
  );
}

function ListEditor({ label, items, onChange, placeholder }: { label: string; items: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1 text-[14px] font-medium">{label}</legend>
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-1">
          <Input aria-label={`${label} ${i + 1}`} value={it} onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} wrapperClassName="flex-1" />
          <IconButton label="Xoá dòng" icon={<Trash2 />} onClick={() => onChange(items.filter((_, j) => j !== i))} />
        </div>
      ))}
      <Button type="button" size="sm" variant="ghost" icon={<Plus className="size-4" aria-hidden />} className="self-start" onClick={() => onChange([...items, ""])}>
        {placeholder}
      </Button>
    </fieldset>
  );
}

function Profile({ voice, owner }: { voice: Voice; owner: boolean }) {
  const edit = useEditVoice();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Required<VoicePatch>>(() => toForm(voice));
  const startEdit = () => {
    setForm(toForm(voice));
    setEditing(true);
  };

  if (editing) {
    return (
      <Card className="flex flex-col gap-3">
        <Textarea label="Tóm tắt cách viết" rows={3} value={form.style_summary ?? ""} onChange={(e) => setForm({ ...form, style_summary: e.target.value })} />
        <Input label="Xưng hô" value={form.pronouns ?? ""} onChange={(e) => setForm({ ...form, pronouns: e.target.value })} />
        <Input label="Độ dài câu, nhịp viết" value={form.sentence_style ?? ""} onChange={(e) => setForm({ ...form, sentence_style: e.target.value })} />
        <ListEditor label="Nên" items={form.rules} onChange={(rules) => setForm({ ...form, rules })} placeholder="Thêm điều nên" />
        <ListEditor label="Tránh" items={form.avoid} onChange={(avoid) => setForm({ ...form, avoid })} placeholder="Thêm điều tránh" />
        <ListEditor label="Từ hay dùng" items={form.vocabulary} onChange={(vocabulary) => setForm({ ...form, vocabulary })} placeholder="Thêm từ" />
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setEditing(false)}>
            Thôi
          </Button>
          <Button
            loading={edit.isPending}
            onClick={() => {
              const clean = (xs: string[]) => xs.map((x) => x.trim()).filter(Boolean);
              edit.mutate(
                { ...form, rules: clean(form.rules), avoid: clean(form.avoid), vocabulary: clean(form.vocabulary) },
                { onSuccess: () => { notifySuccess("Đã lưu hồ sơ giọng"); setEditing(false); } },
              );
            }}
          >
            Lưu
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-[17px] font-bold">{voice.name}</h2>
          <p className="text-[12.5px] text-ink-3">
            Bản {voice.version}
            {voice.trained_at ? ` · học lần cuối ${formatDateTime(voice.trained_at)}` : ""} · {voice.samples_count} mẫu
          </p>
        </div>
        {owner ? (
          <Button size="sm" variant="secondary" onClick={startEdit}>
            Sửa
          </Button>
        ) : null}
      </div>
      {voice.style_summary ? <p className="text-[15px]">{voice.style_summary}</p> : <p className="text-[14px] text-ink-2">Chưa có tóm tắt — dán vài bài cũ để AI học.</p>}
      <Row label="Xưng hô" value={voice.pronouns} />
      <Row label="Câu chữ" value={voice.sentence_style} />
      <Chips label="Nên" items={voice.rules} />
      <Chips label="Tránh" items={voice.avoid} danger />
      <Chips label="Từ hay dùng" items={voice.vocabulary} />
      {voice.examples.length ? (
        <div className="flex flex-col gap-1">
          <SectionLabel>CÂU TIÊU BIỂU</SectionLabel>
          {voice.examples.map((e, i) => (
            <blockquote key={i} className="border-l-2 border-accent pl-3 text-[14px] text-ink-2">
              {e}
            </blockquote>
          ))}
        </div>
      ) : null}
    </Card>
  );
}

function toForm(v: Voice): Required<VoicePatch> {
  return {
    style_summary: v.style_summary ?? "",
    pronouns: v.pronouns ?? "",
    sentence_style: v.sentence_style ?? "",
    rules: v.rules,
    avoid: v.avoid,
    vocabulary: v.vocabulary,
    examples: v.examples,
  };
}

function Row({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <p className="text-[14px]">
      <span className="font-semibold">{label}: </span>
      {value}
    </p>
  );
}

function Chips({ label, items, danger }: { label: string; items: string[]; danger?: boolean }) {
  if (!items.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[13px] font-semibold text-ink-2">{label}</p>
      <ul className="flex flex-wrap gap-1.5">
        {items.map((x, i) => (
          <li key={i} className={danger ? "rounded-sm bg-seal-wash px-2 py-0.5 text-[13px] text-seal" : "rounded-sm bg-soft px-2 py-0.5 text-[13px]"}>
            {x}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LearnCard() {
  const learn = useLearnVoice();
  const [samples, setSamples] = useState("");
  const [notes, setNotes] = useState("");
  const [spoken, setSpoken] = useState("");
  const speech = useSpeech((t) => {
    if (t) setSpoken((cur) => (cur.trim() ? `${cur.trim()} ${t}` : t));
  });
  const parts = samples.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
  const said = spoken.trim();
  return (
    <Card tone="soft" className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Sparkles className="size-4 text-accent" aria-hidden />
        <h2 className="text-[17px] font-bold">Cho AI học thêm</h2>
      </div>
      <Textarea
        label="Dán bài cũ của chị"
        rows={8}
        value={samples}
        onChange={(e) => setSamples(e.target.value)}
        hint={`Mỗi bài cách nhau một dòng trống · ${parts.length} bài`}
        placeholder={"Cả nhà ơi, mình mới thử…\n\nMình dùng hộp cơm này…"}
      />
      {speech.supported ? (
        <div className="flex flex-col gap-2">
          <Textarea
            label="Lời chị nói"
            rows={3}
            value={speech.interim ? `${spoken}${spoken ? " " : ""}${speech.interim}` : spoken}
            onChange={(e) => setSpoken(e.target.value)}
            readOnly={speech.listening}
            error={speech.error ?? undefined}
            hint="Bấm «Nói», kể về một món như đang nói với khách. Chữ chép ra sửa được trước khi học."
            placeholder="Vd: cả nhà ơi, mình mới thử cái hộp cơm này…"
          />
          {speech.listening ? (
            <Button size="sm" variant="danger" className="self-start" icon={<Square className="size-3.5" aria-hidden />} onClick={speech.stop}>
              Đang nghe… bấm để dừng
            </Button>
          ) : (
            <Button size="sm" variant="secondary" className="self-start" icon={<Mic className="size-4" aria-hidden />} onClick={speech.start}>
              Nói
            </Button>
          )}
        </div>
      ) : null}
      <Textarea label="Ghi chú của chị (không bắt buộc)" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Vd: không dùng chữ «siêu phẩm», hay kết bằng câu hỏi" />
      <Button
        loading={learn.isPending}
        disabled={(!parts.length && !notes.trim() && !said) || speech.listening}
        onClick={() =>
          learn.mutate(
            { samples: parts, notes: notes.trim() || undefined, spoken: said ? [said] : [] },
            { onSuccess: (r) => { notifySuccess(r.status === "applied" ? "AI đã cập nhật hồ sơ giọng" : "Đang chờ chị duyệt"); setSamples(""); setNotes(""); setSpoken(""); } },
          )
        }
      >
        Học giọng
      </Button>
      <p className="text-[12.5px] text-ink-2">Lần học nào cũng hoàn tác được ở Nhật ký AI.</p>
    </Card>
  );
}
