"use client";

import { Check, Plus, Search, ShoppingBag, SlidersHorizontal, Trash2, WifiOff } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  Checkbox,
  Chip,
  ChipRow,
  DataList,
  DateTime,
  Dialog,
  EmptyState,
  IconButton,
  ImageBox,
  InlineSelect,
  Input,
  LevelMark,
  LevelTag,
  Money,
  PageHeader,
  ProgressBar,
  RadioGroup,
  ScoreBar,
  Seal,
  SectionLabel,
  Segmented,
  Sheet,
  Skeleton,
  SkeletonList,
  StatTile,
  Switch,
  Tabs,
  Textarea,
  Timeline,
  notifyError,
  notifySuccess,
  useConfirm,
} from "@/components/ui";
import { Brand } from "@/components/layout/brand";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import type { ThemePreference } from "@/lib/theme";
import { useThemePreference } from "@/lib/use-theme";

/* Ảnh mẫu dựng bằng SVG (không dùng ảnh thật của sản phẩm). */
const SAMPLE_IMG =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="#dfe1e8"/><rect x="150" y="70" width="100" height="270" rx="28" fill="#2e3f8f"/><rect x="160" y="52" width="80" height="34" rx="10" fill="#1c1d22"/><rect x="150" y="150" width="100" height="16" fill="#f6f6f2" opacity=".55"/><ellipse cx="200" cy="350" rx="90" ry="10" fill="#1c1d22" opacity=".12"/></svg>`,
  );

const NOW_ISO = "2026-11-25T03:00:00Z";
const PAST_ISO = "2026-11-24T08:00:00Z";

function KitSection({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-t`} className="scroll-mt-6 border-t border-line pt-6">
      <h2 id={`${id}-t`} className="text-xl font-bold">
        {title}
      </h2>
      {note ? <p className="mt-1 text-[14px] text-ink-2">{note}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Row({ label, children, className }: { label?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {label ? <p className="text-[12.5px] font-medium text-ink-3">{label}</p> : null}
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

const COLOR_TOKENS: { name: string; role: string; cls: string }[] = [
  { name: "paper", role: "Nền trang", cls: "bg-paper" },
  { name: "surface", role: "Thẻ, ô nhập", cls: "bg-surface" },
  { name: "soft", role: "Nền phụ", cls: "bg-soft" },
  { name: "soft-2", role: "Hover, chờ ảnh", cls: "bg-soft-2" },
  { name: "line", role: "Đường kẻ", cls: "bg-line" },
  { name: "line-strong", role: "Viền ô nhập", cls: "bg-line-strong" },
  { name: "ink", role: "Chữ chính", cls: "bg-ink" },
  { name: "ink-2", role: "Chữ phụ", cls: "bg-ink-2" },
  { name: "ink-3", role: "Chữ mờ", cls: "bg-ink-3" },
  { name: "accent", role: "Chàm: hành động", cls: "bg-accent" },
  { name: "accent-wash", role: "Nền chàm nhạt", cls: "bg-accent-wash" },
  { name: "seal", role: "Chị quyết · lỗi", cls: "bg-seal" },
  { name: "seal-wash", role: "Nền đỏ son", cls: "bg-seal-wash" },
  { name: "review", role: "AI làm, chị duyệt", cls: "bg-review" },
  { name: "review-wash", role: "Nền vàng nâu", cls: "bg-review-wash" },
  { name: "auto", role: "AI tự làm · xong", cls: "bg-auto" },
  { name: "auto-wash", role: "Nền cổ vịt", cls: "bg-auto-wash" },
];

function Palette({ theme }: { theme: "light" | "dark" }) {
  return (
    <div data-theme={theme} className="rounded-md border border-line bg-paper p-3 text-ink">
      <p className="mb-2 text-[13px] font-semibold">{theme === "light" ? "Sáng" : "Tối"}</p>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
        {COLOR_TOKENS.map((t) => (
          <div key={t.name} className="flex items-center gap-2 rounded-md bg-surface p-1.5">
            <span className={cn("size-8 shrink-0 rounded-sm border border-line", t.cls)} />
            <span className="min-w-0 leading-tight">
              <span className="block truncate font-mono text-[11.5px]">{t.name}</span>
              <span className="block truncate text-[11px] text-ink-2">{t.role}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProductCardSample() {
  return (
    <div className="flex flex-col gap-1.5">
      <ImageBox src={SAMPLE_IMG} priority alt="Ảnh minh hoạ bình giữ nhiệt" overlay={<Seal chosen={1} total={24} size={46} />} />
      <p className="mt-1 text-[15px] leading-snug font-semibold">Bình giữ nhiệt 480 ml</p>
      <Money value={385000} className="text-[15px]" />
      <p className="text-[13px] text-ink-2">Thử 3 tuần · Nhật</p>
    </div>
  );
}

function MiniPreview({ theme }: { theme: "light" | "dark" }) {
  return (
    <div data-theme={theme} className="flex flex-col gap-3 rounded-md border border-line bg-paper p-4 text-ink">
      <div className="flex items-center justify-between">
        <Brand />
        <IconButton label="Giỏ hàng" icon={<ShoppingBag />} count={2} />
      </div>
      <Card tone="soft">
        <p className="text-[14px] font-semibold">Vì sao mình chọn</p>
        <p className="text-[14px] text-ink-2">Giữ nóng 9 tiếng, mình đo 3 lần. Nắp tháo rời, không ám mùi.</p>
      </Card>
      <div className="flex flex-wrap gap-1.5">
        <LevelTag level="owner" />
        <LevelTag level="review" />
        <LevelTag level="auto" />
      </div>
      <ProgressBar value={86} max={120} label="86 trên 120 suất" />
      <div className="flex gap-2">
        <Button size="sm">Đặt trong đợt 12</Button>
        <Button size="sm" variant="secondary">
          Hồ sơ chọn
        </Button>
      </div>
    </div>
  );
}

export function KitShowcase() {
  const [theme, setTheme] = useThemePreference();
  const confirm = useConfirm();
  const [tab, setTab] = useState("cho");
  const [seg, setSeg] = useState<"auto" | "ask" | "off">("ask");
  const [chip, setChip] = useState("all");
  const [select, setSelect] = useState<string | null>("ghn");
  const [sort, setSort] = useState("moi");
  const [radio, setRadio] = useState<string | null>("qr");
  const [sw, setSw] = useState(true);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <main className="mx-auto flex w-full max-w-[64rem] flex-col gap-8 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-24 md:px-8 md:pt-8">
      <PageHeader
        backHref="/desk"
        eyebrow="Hàng Chọn · hệ thiết kế"
        title="Bộ giao diện «Chàm»"
        description="Token và component dùng chung. Mọi màn hình mới lấy từ đây."
      />
      <Segmented<ThemePreference>
        aria-label="Giao diện"
        value={theme}
        onChange={setTheme}
        options={[
          { value: "system", label: "Theo máy" },
          { value: "light", label: "Sáng" },
          { value: "dark", label: "Tối" },
        ]}
        className="self-start"
      />

      <KitSection id="sang-toi" title="Sáng và tối cạnh nhau" note="Cùng một đoạn giao diện, đặt data-theme cục bộ.">
        <div className="grid gap-3 md:grid-cols-2">
          <MiniPreview theme="light" />
          <MiniPreview theme="dark" />
        </div>
      </KitSection>

      <KitSection id="mau" title="Màu" note="Lớp Tailwind: bg-<token>, text-<token>, border-<token>. Bảng màu mặc định của Tailwind đã tắt.">
        <div className="grid gap-3 lg:grid-cols-2">
          <Palette theme="light" />
          <Palette theme="dark" />
        </div>
      </KitSection>

      <KitSection id="chu" title="Chữ" note="Tiêu đề: Bricolage Grotesque, giãn nhẹ 0.01em. Thân: Be Vietnam Pro.">
        <div className="flex flex-col gap-3">
          <p className="font-display text-[40px] leading-[1.05] font-extrabold tracking-display">Ít món, món nào cũng thử</p>
          <h1 className="text-[30px] font-bold">Tiêu đề trang · 26–30px</h1>
          <h2 className="text-xl font-bold">Tiêu đề khối · 20px</h2>
          <h3 className="text-[15px] font-semibold">Tiêu đề thẻ · 15px đậm</h3>
          <p className="max-w-prose text-[16px]">
            Thân bài 16px. Mình thử 5 chiếc bình trong 3 tuần. Chiếc này ở lại vì sáng pha trà, 5 giờ chiều vẫn còn nóng; nắp tháo
            rời nên rửa xong không còn mùi.
          </p>
          <p className="text-[14px] text-ink-2">Chữ phụ 14px · ink-2</p>
          <p className="text-[13px] text-ink-3">Chữ mờ 13px · ink-3, chỉ cho gợi ý</p>
          <p className="font-display text-[22px] font-extrabold tabular-nums">28,4 tr · 86/120 · 1.240</p>
          <SectionLabel>Nhãn nhóm · chữ hoa giãn</SectionLabel>
        </div>
      </KitSection>

      <KitSection id="goc" title="Góc và khoảng cách" note="Góc chuẩn rounded-md = 4px. Khoảng cách theo bội số 4px (gap-2 = 8px, p-4 = 16px).">
        <div className="flex flex-wrap items-end gap-3">
          {[
            ["rounded-sm", "2px"],
            ["rounded-md", "4px · chuẩn"],
            ["rounded-lg", "6px · mép sheet"],
            ["rounded-full", "dấu, chấm"],
          ].map(([cls, label]) => (
            <div key={cls} className="flex flex-col items-center gap-1.5">
              <span className={cn("size-14 border-2 border-accent bg-accent-wash", cls)} />
              <span className="text-[12px] text-ink-2">{label}</span>
            </div>
          ))}
          <div className="ml-2 flex items-end gap-1.5">
            {[1, 2, 3, 4, 6, 8].map((n) => (
              <div key={n} className="flex flex-col items-center gap-1">
                <span className="w-3 bg-ink-3" style={{ height: n * 4 }} />
                <span className="text-[11px] text-ink-3">{n * 4}</span>
              </div>
            ))}
          </div>
        </div>
      </KitSection>

      <KitSection id="nut" title="Nút">
        <div className="flex flex-col gap-4">
          <Row label="Kiểu">
            <Button>Đặt trong đợt 12</Button>
            <Button variant="secondary">Mua mẫu</Button>
            <Button variant="ghost">Bỏ qua</Button>
            <Button variant="danger" icon={<Trash2 className="size-4" />}>
              Loại
            </Button>
          </Row>
          <Row label="Cỡ (sm 36 · md 44 · lg 52)">
            <Button size="sm">Nhỏ</Button>
            <Button size="md">Vừa</Button>
            <Button size="lg">Lớn</Button>
          </Row>
          <Row label="Trạng thái">
            <Button loading>Đang lưu</Button>
            <Button disabled>Không bấm được</Button>
            <ButtonLink href="/desk" variant="secondary">
              Liên kết dạng nút
            </ButtonLink>
          </Row>
          <Row label="IconButton (luôn có label cho trình đọc màn hình)">
            <IconButton label="Tìm" icon={<Search />} />
            <IconButton label="Lọc" icon={<SlidersHorizontal />} variant="secondary" />
            <IconButton label="Thêm" icon={<Plus />} variant="primary" />
            <IconButton label="Giỏ hàng" icon={<ShoppingBag />} count={3} />
          </Row>
          <Button block icon={<Check className="size-4" />} className="md:max-w-sm">
            Duyệt, xếp lịch (block)
          </Button>
        </div>
      </KitSection>

      <KitSection id="o-nhap" title="Ô nhập">
        <div className="grid gap-4 md:grid-cols-2">
          <Input label="Số điện thoại" placeholder="09xx xxx xxx" hint="Số này là khoá tra đơn về sau." inputMode="tel" />
          <Input label="Email" defaultValue="chi@vd" error="Email chưa đúng dạng." />
          <Input aria-label="Tìm trên kệ" placeholder="Bạn đang cần gì? vd. bình nước cho bé" leading={<Search />} />
          <Input label="Giá bán" defaultValue="245000" inputMode="numeric" trailing={<span className="text-[15px]">đ</span>} required />
          <InlineSelect
            label="Hãng vận chuyển"
            value={select}
            onChange={setSelect}
            options={[
              { value: "ghn", label: "Giao Hàng Nhanh", hint: "22.000đ · 1–2 ngày" },
              { value: "ghtk", label: "Giao Hàng Tiết Kiệm", hint: "18.000đ · 2–3 ngày" },
              { value: "self", label: "Tự giao", disabled: true },
            ]}
          />
          <Textarea label="Ghi chú thử hàng" placeholder="Phơi chăn mùa đông không võng…" hint="Ô tự giãn theo nội dung." />
          <div className="flex items-center gap-1 text-[15px]">
            Sắp xếp theo
            <InlineSelect
              appearance="inline"
              aria-label="Sắp xếp"
              value={sort}
              onChange={setSort}
              options={[
                { value: "moi", label: "mới nhất" },
                { value: "diem", label: "điểm cao" },
                { value: "gia", label: "giá về tay" },
              ]}
            />
          </div>
        </div>
      </KitSection>

      <KitSection id="lua-chon" title="Lựa chọn">
        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Checkbox label="Gắn nhãn nội dung do AI tạo" defaultChecked />
            <Checkbox label="Báo khách qua Zalo" description="Mỗi mốc đơn hàng một tin." />
            <Checkbox label="Không bấm được" disabled />
          </div>
          <RadioGroup
            name="thanh-toan"
            legend="Thanh toán"
            value={radio}
            onChange={setRadio}
            options={[
              { value: "qr", label: "Chuyển khoản bằng mã QR", description: "Tự xác nhận khi tiền về." },
              { value: "cod", label: "Trả tiền khi nhận hàng" },
            ]}
          />
          <div className="flex flex-col gap-2">
            <Switch label="Đăng bài đã duyệt theo lịch" description="AI tự đăng đúng giờ đã xếp." checked={sw} onChange={setSw} />
            <Switch label="Không đổi được" checked={false} onChange={() => {}} disabled />
          </div>
          <div className="flex flex-col gap-2">
            <p className="text-[15px]">Soạn và đăng bài mới</p>
            <Segmented
              aria-label="Mức tự chủ"
              value={seg}
              onChange={setSeg}
              options={[
                { value: "auto", label: "Tự làm" },
                { value: "ask", label: "Hỏi chị" },
                { value: "off", label: "Tắt" },
              ]}
            />
          </div>
        </div>
      </KitSection>

      <KitSection id="tab-chip" title="Tabs, Chip, Badge">
        <div className="flex flex-col gap-5">
          <Tabs
            aria-label="Trạng thái đơn"
            value={tab}
            onChange={setTab}
            items={[
              { value: "cho", label: "Chờ thanh toán", count: 3 },
              { value: "ve", label: "Chờ hàng về", count: 86 },
              { value: "giao", label: "Đang giao", count: 12 },
              { value: "xong", label: "Xong" },
            ]}
          />
          <ChipRow>
            {[
              ["all", "Tất cả", 38],
              ["bep", "Bếp", 12],
              ["be", "Cho bé", 9],
              ["ban", "Bàn làm việc", 7],
              ["xa", "Đi xa", 10],
            ].map(([v, l, c]) => (
              <Chip key={v as string} selected={chip === v} count={c as number} onClick={() => setChip(v as string)}>
                {l}
              </Chip>
            ))}
          </ChipRow>
          <div className="flex flex-wrap gap-2">
            <Badge>Trung tính</Badge>
            <Badge tone="accent">Đợt 12 · còn 34 suất</Badge>
            <Badge tone="success">Đã khớp tiền</Badge>
            <Badge tone="warning">Chờ chuyển khoản</Badge>
            <Badge tone="danger">Quá hạn</Badge>
            <Badge tone="outline">Facebook</Badge>
          </div>
        </div>
      </KitSection>

      <KitSection id="muc-dau" title="Mức tự động và con dấu" note="Ba mức phân biệt bằng cả hình (vuông · nửa tròn · tròn) và màu.">
        <div className="flex flex-col gap-5">
          <Row label="LevelTag">
            <LevelTag level="owner" />
            <LevelTag level="review" />
            <LevelTag level="auto" />
          </Row>
          <Row label="Nhãn tuỳ chỉnh · cỡ nhỏ">
            <LevelTag level="review">Chờ duyệt</LevelTag>
            <LevelTag level="owner">Luôn hỏi chị</LevelTag>
            <LevelTag level="auto" size="sm">
              AI đã tự làm · 23 việc
            </LevelTag>
          </Row>
          <Row label="LevelMark (chú giải)">
            <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-2">
              <LevelMark level="owner" /> Chị quyết
            </span>
            <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-2">
              <LevelMark level="review" /> AI làm, chị duyệt
            </span>
            <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-2">
              <LevelMark level="auto" /> AI tự làm
            </span>
          </Row>
          <Row label="Seal">
            <Seal chosen={1} total={24} size={44} />
            <Seal chosen={1} total={24} />
            <Seal chosen={1} total={31} size={72} />
            <Seal size={44} />
          </Row>
        </div>
      </KitSection>

      <KitSection id="the" title="Thẻ và ảnh">
        <div className="flex flex-col gap-5">
          <div className="grid gap-3 md:grid-cols-2">
            <Card>
              <CardHeader title="Card mặc định" aside={<LevelTag level="review" size="sm">Chờ duyệt</LevelTag>} />
              <p className="text-[14px] text-ink-2">Giá bán hộp cơm inox: 245.000đ, biên 34%.</p>
            </Card>
            <Card tone="soft">
              <CardHeader title="Vì sao mình chọn" />
              <ul className="list-disc pl-5 text-[14px] text-ink-2">
                <li>Giữ nóng 9 tiếng, mình đo 3 lần</li>
                <li>Nắp tháo rời, không ám mùi</li>
              </ul>
            </Card>
            <Card tone="accent">
              <SectionLabel>Đợt 12 · đang mở</SectionLabel>
              <p className="mt-1 font-display text-lg font-bold">Đồ bếp gọn cho nhà nhỏ</p>
            </Card>
            <Card tone="danger">
              <CardHeader title="Khách báo bình bị móp khi nhận" aside={<LevelTag level="owner" size="sm" />} />
              <p className="text-[14px] text-ink-2">AI đề xuất: gửi nắp thay miễn phí, hoặc hoàn 50.000đ.</p>
            </Card>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <ProductCardSample />
            <div className="flex flex-col gap-1.5">
              <ImageBox alt="" placeholder="Ảnh chị chụp" overlay={<Seal chosen={1} total={17} size={46} />} />
              <p className="mt-1 text-[15px] leading-snug font-semibold">Hộp cơm inox 3 ngăn</p>
              <Money value={245000} className="text-[15px]" />
              <p className="text-[13px] text-ink-2">Thử 2 tuần · Trung Quốc</p>
            </div>
            <ImageBox alt="" ratio="4/3" placeholder="Tỉ lệ 4/3" />
            <ImageBox alt="" ratio="3/4" placeholder="Tỉ lệ 3/4" />
          </div>
        </div>
      </KitSection>

      <KitSection id="so-lieu" title="Tiền, ngày giờ, số liệu" note="Giờ hiển thị theo Asia/Ho_Chi_Minh.">
        <div className="flex flex-col gap-5">
          <DataList
            className="max-w-sm"
            items={[
              { label: "Money", value: <Money value={385000} /> },
              { label: "Money compact", value: <Money value={3400000} compact /> },
              { label: "Giá cũ", value: <Money value={450000} strike /> },
              { label: "Ngày", value: <DateTime value={NOW_ISO} /> },
              { label: "Thứ, ngày", value: <DateTime value={NOW_ISO} format="weekday" /> },
              { label: "Giờ · ngày", value: <DateTime value={NOW_ISO} format="dateTime" /> },
              { label: "Tương đối", value: <DateTime value={PAST_ISO} format="relative" /> },
            ]}
          />
          <div className="grid grid-cols-3 gap-2 md:max-w-lg">
            <StatTile value="9" label="đơn mới" />
            <StatTile value={<Money value={3400000} compact />} label="tiền về" />
            <StatTile value="86/120" label="Đợt 12" hint="còn 2 ngày" />
          </div>
          <div className="flex max-w-md flex-col gap-2">
            <ScoreBar label="Chất lượng" score={22} max={25} />
            <ScoreBar label="Khác biệt" score={9} max={15} />
            <ScoreBar label="Vận chuyển" score={2} max={5} />
          </div>
          <div className="flex max-w-md flex-col gap-3">
            <ProgressBar value={86} max={120} label="86 trên 120 suất" />
            <ProgressBar value={9} max={14} label="Ngày thử thứ 9 trong 14" tone="success" size="sm" />
          </div>
        </div>
      </KitSection>

      <KitSection id="hanh-trinh" title="Timeline và DataList">
        <div className="grid gap-6 md:grid-cols-2">
          <Timeline
            items={[
              { title: "Đã nhận đơn, đã thanh toán", meta: "25/11", status: "done" },
              { title: "Chốt đợt 12, đã đặt nhà cung cấp", meta: "28/11", status: "done" },
              { title: "Rời kho Osaka", meta: "04/12", status: "current" },
              { title: "Về tới Hà Nội, chị kiểm từng món", meta: "Dự kiến 10/12", status: "todo" },
              { title: "Giao cho bạn", meta: "Dự kiến 12/12", status: "todo" },
            ]}
          />
          <Card>
            <DataList
              items={[
                { label: "Tạm tính", value: <Money value={385000} /> },
                { label: "Phí giao", value: <Money value={22000} /> },
                { label: "Tổng", value: <Money value={407000} />, strong: true },
              ]}
            />
          </Card>
        </div>
      </KitSection>

      <KitSection id="trang-thai" title="Chờ tải và trạng thái trống">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-40" />
            <SkeletonList rows={2} />
          </div>
          <div className="flex flex-col gap-3">
            <EmptyState icon={<Search />} title="Chưa có ứng viên" description="Ra đề săn hàng để AI bắt đầu tìm." action={<Button size="sm">Ra đề</Button>} />
            <EmptyState tone="error" icon={<WifiOff />} title="Chưa kết nối được máy chủ" description="Kiểm tra mạng rồi thử lại." />
          </div>
        </div>
      </KitSection>

      <KitSection id="lop-noi" title="Sheet, Dialog, xác nhận, thông báo" note="Không dùng alert/confirm/prompt của trình duyệt.">
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setSheetOpen(true)}>
            Mở Sheet
          </Button>
          <Button variant="secondary" onClick={() => setDialogOpen(true)}>
            Mở Dialog
          </Button>
          <Button
            variant="secondary"
            onClick={async () => {
              const ok = await confirm({
                title: "Loại món này?",
                message: "Lý do loại sẽ được lưu để hiện ở trang Hồ sơ chọn.",
                confirmLabel: "Loại",
                tone: "danger",
              });
              if (ok) notifySuccess("Đã loại, lý do đã lưu.");
            }}
          >
            useConfirm()
          </Button>
          <Button variant="secondary" onClick={() => notifySuccess("Đã duyệt 2 bài cho Đợt 12.")}>
            notifySuccess
          </Button>
          <Button variant="secondary" onClick={() => notifyError(new ApiError("Không tìm thấy dữ liệu.", 404))}>
            notifyError
          </Button>
        </div>
        <Sheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title="Lọc ứng viên"
          description="Trên điện thoại trượt từ dưới lên; trên máy tính nổi giữa màn hình."
          footer={
            <>
              <Button variant="secondary" onClick={() => setSheetOpen(false)}>
                Huỷ
              </Button>
              <Button onClick={() => setSheetOpen(false)}>Áp dụng</Button>
            </>
          }
        >
          <div className="flex flex-col gap-3">
            <Input label="Giá về tay tối đa" defaultValue="300000" inputMode="numeric" trailing={<span className="text-[15px]">đ</span>} />
            <Checkbox label="Chỉ hàng Nhật" />
            <Checkbox label="Đánh giá từ 4,7" defaultChecked />
          </div>
        </Sheet>
        <Dialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          title="Đổi giá bán"
          description="Giá mới áp dụng cho đơn đặt sau thời điểm lưu."
          footer={
            <>
              <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                Huỷ
              </Button>
              <Button
                onClick={() => {
                  setDialogOpen(false);
                  notifySuccess("Đã đổi giá.");
                }}
              >
                Lưu
              </Button>
            </>
          }
        >
          <Input label="Giá bán" defaultValue="245000" inputMode="numeric" trailing={<span className="text-[15px]">đ</span>} />
        </Dialog>
      </KitSection>
    </main>
  );
}
