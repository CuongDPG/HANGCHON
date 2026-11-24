"use client";

import { ErrorView } from "@/components/layout/error-view";

export default function StoreError(props: { error: unknown; retry: () => void }) {
  return <ErrorView {...props} />;
}
