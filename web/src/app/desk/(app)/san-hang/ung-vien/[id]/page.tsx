import { Suspense } from "react";
import { ProfileScreen } from "@/components/assessment/profile-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";

export const metadata = { title: "Hồ sơ thẩm định" };

/** Hồ sơ thẩm định một ứng viên (b1–b7) + Loại / Mua mẫu / Chọn. */
export default function CandidateProfilePage({ params }: PageProps<"/desk/san-hang/ung-vien/[id]">) {
  return (
    <Suspense fallback={<DeskPageFallback backHref="/desk/san-hang" rows={5} />}>
      <Profile params={params} />
    </Suspense>
  );
}

async function Profile({ params }: { params: PageProps<"/desk/san-hang/ung-vien/[id]">["params"] }) {
  const { id } = await params;
  return <ProfileScreen id={id} />;
}
