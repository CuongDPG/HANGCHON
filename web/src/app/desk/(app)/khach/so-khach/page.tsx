import { Suspense } from "react";
import { CustomersScreen } from "@/components/crm/customers-screen";
import { DeskPageFallback } from "@/components/desk/desk-page-fallback";
import { KHACH_SECTIONS } from "@/lib/desk-sections";

export const metadata = { title: "Sổ khách" };

export default function CustomerBookPage() {
  return (
    <Suspense fallback={<DeskPageFallback sections={KHACH_SECTIONS} active="book" rows={4} />}>
      <CustomersScreen />
    </Suspense>
  );
}
