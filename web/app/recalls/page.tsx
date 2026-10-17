import type { Metadata } from "next";
import { Suspense } from "react";
import { RecallsView } from "@/components/views/recalls";

export const metadata: Metadata = { title: "Recalls" };

export default function Page() {
  return (
    <Suspense>
      <RecallsView />
    </Suspense>
  );
}
