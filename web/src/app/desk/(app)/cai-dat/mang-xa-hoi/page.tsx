import { Suspense } from "react";
import { SocialAccountsScreen } from "@/components/control/social-accounts-screen";

export const metadata = { title: "Mạng xã hội" };

export default function DeskSocialAccountsPage() {
  return (
    <Suspense>
      <SocialAccountsScreen />
    </Suspense>
  );
}
