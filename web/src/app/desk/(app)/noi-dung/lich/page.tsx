import { Suspense } from "react";
import { CalendarScreen } from "@/components/content/calendar-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { CONTENT_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Lịch đăng" };

export default function Page() {
  return (
    <Suspense fallback={<DeskPageFallback sections={CONTENT_SECTIONS} active="calendar" rows={4} />}>
      <CalendarScreen />
    </Suspense>
  );
}
