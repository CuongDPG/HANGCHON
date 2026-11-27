"use client";

import { PenLine, RotateCw, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import {
  Button,
  Card,
  DateTime,
  EmptyState,
  IconButton,
  Input,
  LevelTag,
  PageHeader,
  ProgressBar,
  Sheet,
  SkeletonList,
  Textarea,
  notifySuccess,
} from "@/components/ui";
import { useRetrainTaste, useTasteProfiles, useUpdateTaste, type TasteProfile, type Trait } from "@/lib/api/selection";

/** «AI đang hiểu gu chị thế nào» (c6): AI tổng hợp từ lịch sử chọn/loại, chị sửa được. */
export function TasteScreen() {
  const { data, isPending, error } = useTasteProfiles();
  const retrain = useRetrainTaste();
  const [editing, setEditing] = useState<TasteProfile | null>(null);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="AI hiểu gu chị thế nào"
        backHref="/desk/ban-chon"
        actions={
          <Button
            size="sm"
            variant="secondary"
            loading={retrain.isPending}
            icon={<RotateCw className="size-4" aria-hidden />}
            onClick={async () => {
              await retrain.mutateAsync();
              notifySuccess("AI đã học lại từ các quyết định");
            }}
          >
            Học lại
          </Button>
        }
      />
      {isPending ? (
        <SkeletonList rows={2} />
      ) : error ? (
        <EmptyState tone="error" title="Chưa tải được" description={error.message} />
      ) : !data.length || data.every((p) => !p.summary && !p.pending_count) ? (
        <EmptyState icon={<Sparkles />} title="AI chưa đủ dữ liệu" description="Chọn hoặc loại vài món trên bàn chọn để AI bắt đầu học gu của chị." />
      ) : (
        <ul className="flex flex-col gap-3">
          {data.map((p) => (
            <li key={p.id}>
              <ProfileCard p={p} onEdit={() => setEditing(p)} />
            </li>
          ))}
        </ul>
      )}
      <Sheet open={!!editing} onClose={() => setEditing(null)} title="Sửa gu AI hiểu" description={editing?.category_name ?? "Chung cho mọi nhóm"}>
        {editing ? <TasteForm key={editing.id + editing.version} p={editing} onClose={() => setEditing(null)} /> : null}
      </Sheet>
    </div>
  );
}

function ProfileCard({ p, onEdit }: { p: TasteProfile; onEdit: () => void }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold">{p.category_name ?? "Chung cho mọi nhóm"}</h2>
          <p className="text-[13px] text-ink-2">
            Học từ {p.sample_count} quyết định · bản {p.version}
            {p.trained_at ? (
              <>
                {" · "}
                <DateTime value={p.trained_at} format="relative" />
              </>
            ) : null}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {p.owner_edited ? <LevelTag level="owner" size="sm">Chị đã sửa</LevelTag> : <LevelTag level="auto" size="sm" />}
          <IconButton size="sm" label="Sửa gu" icon={<PenLine />} onClick={onEdit} />
        </div>
      </div>
      {p.summary ? <p className="text-[15px] leading-relaxed">{p.summary}</p> : <p className="text-[14px] text-ink-2">AI chưa tổng hợp lần nào.</p>}
      {p.pending_count ? <p className="text-[13px] text-review">{p.pending_count} quyết định mới đang chờ AI học (mỗi giờ).</p> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <TraitList title="Chị hay chọn" traits={p.likes} tone="success" />
        <TraitList title="Chị hay loại vì" traits={p.dislikes} tone="danger" />
      </div>
    </Card>
  );
}

function TraitList({ title, traits, tone }: { title: string; traits: Trait[]; tone: "success" | "danger" }) {
  return (
    <div>
      <h3 className="mb-2 text-[14px] font-semibold">{title}</h3>
      {traits.length ? (
        <ul className="flex flex-col gap-2">
          {traits.map((t) => (
            <li key={t.trait} className="grid grid-cols-[minmax(0,1fr)_4rem] items-center gap-3 text-[14px]">
              <span>{t.trait}</span>
              <ProgressBar value={Math.abs(t.weight)} max={1} size="sm" tone={tone} label={`${t.trait}: mức ${Math.round(Math.abs(t.weight) * 100)}%`} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[14px] text-ink-3">Chưa có.</p>
      )}
    </div>
  );
}

function TasteForm({ p, onClose }: { p: TasteProfile; onClose: () => void }) {
  const [summary, setSummary] = useState(p.summary ?? "");
  const [likes, setLikes] = useState<Trait[]>(p.likes);
  const [dislikes, setDislikes] = useState<Trait[]>(p.dislikes.map((t) => ({ ...t, weight: Math.abs(t.weight) })));
  const save = useUpdateTaste();
  return (
    <div className="flex flex-col gap-4">
      <Textarea label="AI hiểu gu chị là" value={summary} onChange={(e) => setSummary(e.target.value)} rows={4} />
      <TraitEditor title="Chị hay chọn" traits={likes} onChange={setLikes} />
      <TraitEditor title="Chị hay loại vì" traits={dislikes} onChange={setDislikes} />
      <p className="text-[13px] text-ink-2">Lần học sau, AI giữ các điều chị đã sửa và chỉ bổ sung điều mới.</p>
      <div className="flex justify-end gap-2 border-t border-line pt-3 max-md:[&>*]:flex-1">
        <Button variant="secondary" onClick={onClose}>
          Huỷ
        </Button>
        <Button
          loading={save.isPending}
          onClick={async () => {
            await save.mutateAsync({
              id: p.id,
              summary,
              likes: likes.filter((t) => t.trait.trim()),
              dislikes: dislikes.filter((t) => t.trait.trim()).map((t) => ({ ...t, weight: -Math.abs(t.weight) })),
            });
            notifySuccess("Đã lưu, AI sẽ theo cách chị sửa");
            onClose();
          }}
        >
          Lưu
        </Button>
      </div>
    </div>
  );
}

function TraitEditor({ title, traits, onChange }: { title: string; traits: Trait[]; onChange: (t: Trait[]) => void }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{title}</legend>
      {traits.map((t, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            aria-label={`${title} ${i + 1}`}
            value={t.trait}
            onChange={(e) => onChange(traits.map((x, j) => (j === i ? { ...x, trait: e.target.value } : x)))}
            wrapperClassName="flex-1"
          />
          <IconButton size="sm" label="Bỏ" icon={<Trash2 />} onClick={() => onChange(traits.filter((_, j) => j !== i))} />
        </div>
      ))}
      <Button size="sm" variant="ghost" className="self-start" onClick={() => onChange([...traits, { trait: "", weight: 0.6 }])}>
        + Thêm
      </Button>
    </fieldset>
  );
}
