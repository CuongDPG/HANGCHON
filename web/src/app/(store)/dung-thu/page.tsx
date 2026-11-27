import type { Metadata } from "next";
import { TesterSignup } from "@/components/crm/tester-signup";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = {
  title: "Sổ người dùng thử",
  description: "Đăng ký một lần để được mời dùng thử những món mình đang thử trước khi bán.",
  alternates: { canonical: "/dung-thu" },
};

/** Sổ người dùng thử («Mời thử cùng»): khách đăng ký một lần, không cần tài khoản. */
export default function TesterSignupPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader
        title="Sổ người dùng thử"
        description="Có món mình đang dùng thử trước khi bán, mình mời vài bạn thử cùng: bạn mua giá thường, gửi cảm nhận đúng hạn thì được hoàn một phần tiền."
      />
      <TesterSignup />
    </div>
  );
}
