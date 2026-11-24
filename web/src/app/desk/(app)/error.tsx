"use client";

import { ErrorView } from "@/components/layout/error-view";

export default function DeskError(props: { error: unknown; retry: () => void }) {
  return <ErrorView {...props} />;
}
