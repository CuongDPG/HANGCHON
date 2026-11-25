"use client";

import { CircleCheck, CircleX, PlugZap, RotateCw, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Chip,
  ChipRow,
  DataList,
  DateTime,
  EmptyState,
  InlineSelect,
  Input,
  PageHeader,
  SectionLabel,
  Segmented,
  SkeletonList,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { isOwner, useSession } from "@/lib/api/auth";
import {
  useAIConfig,
  useClearAIKey,
  useSaveAIConfig,
  useTestAIConfig,
  type AIConfig,
  type AIConfigInput,
  type AIEffort,
  type AIProviderInfo,
  type AITestResult,
} from "@/lib/api/control";
import { formatNumber, formatVnd } from "@/lib/format";
import { OwnerOnly } from "./settings-screens";

const EFFORT_LABELS: Record<AIEffort, string> = { low: "Thấp", medium: "Vừa", high: "Cao", max: "Tối đa" };
const TIERS = [
  { key: "smart", title: "Việc khó", hint: "Thẩm định, viết bài, phân tích — cần model giỏi." },
  { key: "fast", title: "Việc nhanh", hint: "Phân loại, tóm tắt ngắn, trả lời mẫu — cần nhanh, rẻ." },
] as const;

/** Cài đặt → «AI và khoá API»: chọn nhà cung cấp AI, khoá API (mã hoá khi lưu), model và độ kỹ từng tầng, trần tháng. */
export function AIConfigScreen() {
  const { user } = useSession();
  const owner = isOwner(user);
  const { data, isPending, error, refetch } = useAIConfig(owner);
  if (user && !owner) return <OwnerOnly title="AI và khoá API" />;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        backHref="/desk/cai-dat"
        title="AI và khoá API"
        description="Chọn nhà cung cấp AI, khoá API và model. Khoá được mã hoá khi lưu, chỉ hiện dạng che."
      />
      {isPending ? (
        <SkeletonList rows={4} />
      ) : error ? (
        <EmptyState
          tone="error"
          title="Chưa tải được cấu hình AI"
          description={error.message}
          action={
            <Button variant="secondary" icon={<RotateCw className="size-4" />} onClick={() => refetch()}>
              Thử lại
            </Button>
          }
        />
      ) : (
        <AIConfigBody key={`${data.provider}:${data.source}`} data={data} />
      )}
    </div>
  );
}

type Draft = {
  api_key: string;
  base_url: string;
  model_smart: string;
  model_fast: string;
  effort_smart: AIEffort;
  effort_fast: AIEffort;
};

function draftOf(p: AIProviderInfo): Draft {
  const effort = (v: string | null, fallback: AIEffort): AIEffort => (v && v in EFFORT_LABELS ? (v as AIEffort) : fallback);
  return {
    api_key: "",
    base_url: p.base_url ?? "",
    model_smart: p.model_smart,
    model_fast: p.model_fast,
    effort_smart: effort(p.effort_smart, "medium"),
    effort_fast: effort(p.effort_fast, "low"),
  };
}

function AIConfigBody({ data }: { data: AIConfig }) {
  const confirm = useConfirm();
  const save = useSaveAIConfig();
  const test = useTestAIConfig();
  const clearKey = useClearAIKey();
  const [provider, setProvider] = useState(data.provider);
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => Object.fromEntries(data.providers.map((p) => [p.name, draftOf(p)])));
  const [budget, setBudget] = useState(String(data.monthly_budget_vnd));
  const [activate, setActivate] = useState(true);
  const [results, setResults] = useState<{ provider: string; results: AITestResult[] } | null>(null);

  const info = data.providers.find((p) => p.name === provider) ?? data.providers[0];
  const active = data.providers.find((p) => p.name === data.provider);
  const draft = drafts[info.name];
  const isFake = info.name === "fake";
  const switching = info.name !== data.provider || data.source !== "settings";
  const budgetVnd = Number(budget.replace(/\D/g, "") || 0);
  const set = (patch: Partial<Draft>) => setDrafts((d) => ({ ...d, [info.name]: { ...d[info.name], ...patch } }));

  function input(): AIConfigInput {
    return {
      provider: info.name,
      api_key: info.needs_key ? draft.api_key.trim() || null : null,
      base_url: info.needs_base_url ? draft.base_url.trim() || null : null,
      model_smart: isFake ? null : draft.model_smart.trim() || null,
      model_fast: isFake ? null : draft.model_fast.trim() || null,
      effort_smart: isFake ? null : draft.effort_smart,
      effort_fast: isFake ? null : draft.effort_fast,
    };
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    const doActivate = !switching || activate;
    if (switching && doActivate && !isFake) {
      const ok = await confirm({
        title: `Chuyển sang dùng ${info.label}?`,
        message: "Mọi việc AI từ giờ gọi nhà cung cấp này và tính tiền vào trần tháng.",
        confirmLabel: "Lưu và chuyển",
      });
      if (!ok) return;
    }
    await save.mutateAsync({ ...input(), monthly_budget_vnd: budgetVnd, activate: doActivate });
    set({ api_key: "" });
    notifySuccess(doActivate ? `Đã lưu, đang dùng ${info.label}` : `Đã lưu cấu hình ${info.label}`);
  }

  async function onTest() {
    setResults(null);
    try {
      setResults(await test.mutateAsync(input()));
    } catch {
      /* lỗi đã hiện bằng thông báo */
    }
  }

  async function onClearKey() {
    const ok = await confirm({
      title: `Xoá khoá ${info.label} đã lưu?`,
      message: "AI sẽ dùng khoá trong biến môi trường của máy chủ (nếu có), không thì báo thiếu khoá.",
      confirmLabel: "Xoá khoá",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await clearKey.mutateAsync(info.name);
      notifySuccess("Đã xoá khoá");
    } catch (err) {
      notifyError(err);
    }
  }

  return (
    <>
      <Card tone="soft" className="flex flex-col gap-2" aria-label="Đang dùng">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[15px] font-semibold">Đang dùng: {data.provider === "fake" ? "AI giả" : (active?.label ?? data.provider)}</p>
          <SourceBadge provider={data.provider} source={data.source} />
        </div>
        {data.provider === "fake" ? (
          <p className="text-[14px] text-ink-2">AI giả trả dữ liệu mẫu để chạy thử: không gọi ra ngoài, không tốn tiền.</p>
        ) : active ? (
          <DataList
            items={[
              { label: "Việc khó", value: <span className="break-all">{active.model_smart}</span> },
              { label: "Việc nhanh", value: <span className="break-all">{active.model_fast}</span> },
            ]}
          />
        ) : null}
      </Card>

      <form onSubmit={onSave} className="flex flex-col gap-5">
        <fieldset className="flex min-w-0 flex-col gap-3">
          <SectionLabel>Nhà cung cấp</SectionLabel>
          <InlineSelect
            label="Nhà cung cấp AI"
            value={provider}
            onChange={(v) => {
              setProvider(v);
              setResults(null);
            }}
            options={data.providers.map((p) => ({
              value: p.name,
              label: p.label,
              hint: p.name === data.provider ? "đang dùng" : p.has_key ? `có khoá ${p.key_hint ?? ""}`.trim() : p.needs_key ? "chưa có khoá" : undefined,
            }))}
          />
          {info.needs_key ? (
            <div className="flex flex-col gap-2">
              <Input
                label="Khoá API"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={draft.api_key}
                onChange={(e) => set({ api_key: e.target.value })}
                placeholder={info.has_key ? "Để trống để giữ khoá hiện có" : info.key_placeholder || "Dán khoá API"}
                hint={<KeyStatus info={info} />}
              />
              {info.key_source === "settings" ? (
                <Button type="button" size="sm" variant="ghost" icon={<Trash2 className="size-4" />} onClick={onClearKey} loading={clearKey.isPending} className="self-start">
                  Xoá khoá
                </Button>
              ) : null}
            </div>
          ) : null}
          {info.needs_base_url ? (
            <Input
              label="Base URL"
              inputMode="url"
              spellCheck={false}
              value={draft.base_url}
              onChange={(e) => set({ base_url: e.target.value })}
              placeholder={info.default_base_url ?? "https://…"}
              hint="Để trống là dùng địa chỉ mặc định."
            />
          ) : null}
          {isFake ? <p className="text-[14px] text-ink-2">AI giả không cần khoá, không gọi ra ngoài. Dùng để chạy thử.</p> : null}
        </fieldset>

        {!isFake
          ? TIERS.map((t) => {
              const modelKey = `model_${t.key}` as const;
              const effortKey = `effort_${t.key}` as const;
              return (
                <fieldset key={t.key} className="flex min-w-0 flex-col gap-3">
                  <SectionLabel>{t.title}</SectionLabel>
                  <Input
                    label={`Model ${t.title.toLowerCase()}`}
                    spellCheck={false}
                    autoCapitalize="off"
                    value={draft[modelKey]}
                    onChange={(e) => set({ [modelKey]: e.target.value })}
                    placeholder={info.model_suggestions[0] ?? "vd. hãng/tên-model"}
                    hint={info.model_suggestions.length ? t.hint : `${t.hint} Gõ đúng tên model trên ${info.label}.`}
                  />
                  {info.model_suggestions.length ? (
                    <ChipRow>
                      {info.model_suggestions.map((m) => (
                        <Chip key={m} selected={draft[modelKey] === m} onClick={() => set({ [modelKey]: m })}>
                          {m}
                        </Chip>
                      ))}
                    </ChipRow>
                  ) : null}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[14px] font-medium text-ink">Độ kỹ</span>
                    <Segmented
                      aria-label={`Độ kỹ ${t.title.toLowerCase()}`}
                      value={draft[effortKey]}
                      onChange={(v) => set({ [effortKey]: v })}
                      options={data.efforts.map((v) => ({ value: v, label: EFFORT_LABELS[v] }))}
                      block
                      size="sm"
                    />
                  </div>
                </fieldset>
              );
            })
          : null}

        <fieldset className="flex min-w-0 flex-col gap-3">
          <SectionLabel>Trần chi phí</SectionLabel>
          <Input
            label="Trần mỗi tháng"
            inputMode="numeric"
            trailing="đ"
            value={budget === "" ? "" : formatNumber(budgetVnd)}
            onChange={(e) => setBudget(e.target.value)}
            hint={`Chạm trần thì AI dừng và hỏi chị. Để 0 nếu không muốn giới hạn.${data.budget_source === "env" ? " Đang theo biến môi trường." : ""}`}
          />
        </fieldset>

        {switching ? (
          <Checkbox
            label={`Chuyển sang dùng ${info.label} khi lưu`}
            description="Bỏ chọn nếu chỉ muốn lưu sẵn khoá, chưa đổi."
            checked={activate}
            onChange={(e) => setActivate(e.target.checked)}
          />
        ) : null}

        {results && results.provider === info.name ? <TestResults results={results.results} /> : null}

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" icon={<PlugZap className="size-4" />} loading={test.isPending} onClick={onTest}>
            Kiểm tra kết nối
          </Button>
          <Button type="submit" loading={save.isPending}>
            Lưu
          </Button>
        </div>
        {!isFake ? (
          <p className="text-[13px] text-ink-2">
            Kiểm tra kết nối gửi một câu rất ngắn tới từng model bằng thông tin đang nhập (chưa cần lưu), có tốn một ít tiền.
          </p>
        ) : null}
      </form>
    </>
  );
}

function SourceBadge({ provider, source }: { provider: string; source: AIConfig["source"] }) {
  if (provider === "fake") return <Badge tone="warning">AI giả</Badge>;
  return source === "settings" ? <Badge tone="accent">Theo Cài đặt</Badge> : <Badge tone="outline">Theo biến môi trường</Badge>;
}

function KeyStatus({ info }: { info: AIProviderInfo }) {
  if (!info.has_key) return <>Chưa có khoá.</>;
  if (info.key_source === "env")
    return (
      <>
        Đang dùng khoá trong biến môi trường máy chủ: <span className="font-mono">{info.key_hint}</span>. Nhập khoá mới để lưu ở Cài đặt.
      </>
    );
  return (
    <>
      Đã lưu (mã hoá): <span className="font-mono">{info.key_hint}</span>
      {info.key_updated_at ? (
        <>
          {" "}
          · đổi <DateTime value={info.key_updated_at} format="dateTime" />
          {info.key_updated_by ? ` bởi ${info.key_updated_by}` : ""}
        </>
      ) : null}
    </>
  );
}

function TestResults({ results }: { results: AITestResult[] }) {
  return (
    <Card className="flex flex-col gap-3" aria-label="Kết quả kiểm tra">
      <p className="text-[15px] font-semibold">Kết quả kiểm tra</p>
      <ul className="flex flex-col gap-3">
        {results.map((r) => (
          <li key={r.tier} className="flex items-start gap-2.5">
            {r.ok ? <CircleCheck className="mt-0.5 size-5 shrink-0 text-auto" aria-hidden /> : <CircleX className="mt-0.5 size-5 shrink-0 text-seal" aria-hidden />}
            <div className="min-w-0 flex-1">
              <p className="text-[15px]">
                <b>{r.tier === "smart" ? "Việc khó" : "Việc nhanh"}</b> · {r.ok ? "Được" : "Không được"}
              </p>
              <p className="text-[13px] break-all text-ink-2">
                {r.model} · {formatNumber(r.latency_ms)} ms{r.ok && r.cost_vnd ? ` · ${formatVnd(r.cost_vnd)}` : ""}
              </p>
              {r.error ? <p className="mt-0.5 text-[14px] text-seal">{r.error}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
