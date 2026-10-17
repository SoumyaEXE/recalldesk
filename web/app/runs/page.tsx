import type { Metadata } from "next";
import { Suspense } from "react";
import { RunsView } from "@/components/views/runs";

export const metadata: Metadata = { title: "Workflow runs" };

export default function Page() {
  return (
    <Suspense>
      <RunsView />
    </Suspense>
  );
}
