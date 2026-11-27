import { Suspense } from "react";
import { InboxScreen } from "@/components/inbox/inbox-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { KHACH_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Hộp thư" };

export default function DeskCustomersPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={KHACH_SECTIONS} active="inbox" rows={4} />}>
      <InboxScreen />
    </Suspense>
  );
}
