import type { Metadata } from "next";
import { RunsView } from "@/components/views/runs";

export const metadata: Metadata = { title: "Workflow runs" };

export default function Page() {
  return <RunsView />;
}
