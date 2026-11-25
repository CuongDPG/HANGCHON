import type { Metadata } from "next";
import { UserRound } from "lucide-react";
import { Suspense } from "react";
import { JsonLd } from "@/components/store/json-ld";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { catalogApi, siteUrl, type About } from "@/lib/api/catalog";
import { errorMessage } from "@/lib/api/client";
import { formatNumber } from "@/lib/format";
import { pickerName } from "@/lib/picker";

export const metadata: Metadata = {
  title: "Về người chọn",
  description: "Ai chọn từng món ở Hàng Chọn và chọn theo nguyên tắc nào.",
  alternates: { canonical: "/ve-nguoi-chon" },
};

/** Về người chọn: trang bảo lãnh — người chọn là ai, chọn theo nguyên tắc nào, AI làm gì. Số liệu lấy thẳng từ Bàn chọn. */
export default function AboutPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <AboutBody />
    </Suspense>
  );
}

async function AboutBody() {
  let a: About;
  try {
    a = await catalogApi.about();
  } catch (err) {
    return <EmptyState tone="error" title="Chưa tải được trang" description={errorMessage(err)} />;
  }
  const url = siteUrl("/ve-nguoi-chon");
  // chưa đặt tên trong Cài đặt (store.picker_name) thì API trả tên trung tính mặc định
  const named = pickerName(a.picker_name) !== null;
  const jsonld = [
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      "@id": `${siteUrl()}#org`,
      name: a.store_name,
      url: siteUrl(),
      description: a.tagline,
      founder: { "@id": `${url}#person` },
    },
    {
      "@context": "https://schema.org",
      "@type": "Person",
      "@id": `${url}#person`,
      name: a.picker_name,
      description: a.intro,
      jobTitle: "Người chọn hàng",
      worksFor: { "@id": `${siteUrl()}#org` },
      url,
    },
  ];
  const ratio = a.stats.ratio_pct !== null ? `${a.stats.ratio_pct.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%` : "—";
  return (
    <div className="flex flex-col gap-6">
      <JsonLd data={jsonld} />
      <header className="flex items-center gap-4">
        <span className="grid size-16 shrink-0 place-items-center rounded-full bg-soft text-ink-2" aria-hidden>
          <UserRound className="size-7" />
        </span>
        <h1 className="text-[24px] leading-tight font-bold [text-wrap:balance] md:text-[30px]">
          {named ? `Mình là ${a.picker_name}, người chọn từng món ở đây` : "Người chọn từng món ở đây"}
        </h1>
      </header>
      <p className="text-[16px] leading-relaxed">{a.intro}</p>

      <dl className="grid grid-cols-3 gap-2">
        {[
          [formatNumber(a.stats.viewed), "món đã xem"],
          [formatNumber(a.stats.chosen), "món được chọn"],
          [ratio, "tỉ lệ chọn"],
        ].map(([v, l]) => (
          <div key={l} className="flex flex-col rounded-md border border-line bg-surface px-3 py-3">
            <dd className="order-1 font-display text-[26px] leading-none font-extrabold tabular-nums">{v}</dd>
            <dt className="order-2 mt-1 text-[13px] text-ink-2">{l}</dt>
          </div>
        ))}
      </dl>
      <p className="-mt-3 text-[12.5px] text-ink-3">Con số lấy thẳng từ bàn chọn của mình, tự cập nhật.</p>

      {a.how_we_choose.length ? (
        <Card>
          <h2 className="text-[17px] font-bold">Cách mình chọn</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[15px]">
            {a.how_we_choose.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </Card>
      ) : null}
      <Card>
        <h2 className="text-[17px] font-bold">Mình không bán</h2>
        <p className="mt-1.5 text-[15px]">{a.not_selling}</p>
        {a.not_selling_rules.length ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[14px] text-ink-2">
            {a.not_selling_rules.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        ) : null}
      </Card>
    </div>
  );
}
