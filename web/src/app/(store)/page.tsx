import { HandHelping, Hourglass, Stamp } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/feedback";
import { Seal } from "@/components/ui/seal";

/** Trang chủ — hướng B «Kệ hàng đã chọn». Lưới sản phẩm thật do màn hình Kệ hàng (e1, e2) làm sau. */
export default function ShelfPage() {
  return (
    <div className="flex flex-col gap-8">
      <section className="grid items-center gap-6 md:grid-cols-[1fr_auto] md:gap-10">
        <div>
          <p className="text-[13px] font-semibold tracking-[0.08em] text-accent uppercase">Kệ hàng đã chọn</p>
          <h1 className="mt-2 text-[clamp(26px,7.2vw,34px)] leading-[1.12] font-extrabold md:text-[48px]">
            <span className="block">Ít món thôi.</span>
            <span className="block">Món nào cũng đã dùng thử.</span>
          </h1>
          <p className="mt-3 max-w-prose text-[16px] text-ink-2 md:text-[17px]">
            Mỗi món trên kệ được mua bằng tiền thật, dùng ít nhất hai tuần, rồi mới được đóng dấu. Cả điều chưa ưng cũng
            được ghi lại.
          </p>
        </div>
        <div className="flex items-center gap-4 rounded-md border border-line bg-surface p-4 md:w-72 md:flex-col md:items-start">
          <Seal chosen={1} total={24} size={64} />
          <p className="text-[14px] text-ink-2">
            <span className="font-semibold text-ink">Con dấu ĐÃ CHỌN 1/24</span> nghĩa là xem 24 món cùng loại, chỉ giữ lại 1.
          </p>
        </div>
      </section>

      <EmptyState
        icon={<Stamp />}
        title="Kệ hàng đang được xếp"
        description="Những món đầu tiên còn đang trong thời gian dùng thử. Bạn đang cần món gì, cứ nhờ chị tìm giúp."
        action={
          <>
            <ButtonLink href="/nho-tim" icon={<HandHelping className="size-4" />}>
              Nhờ chị tìm
            </ButtonLink>
            <ButtonLink href="/dot" variant="secondary" icon={<Hourglass className="size-4" />}>
              Xem đợt gom
            </ButtonLink>
          </>
        }
      />
    </div>
  );
}
