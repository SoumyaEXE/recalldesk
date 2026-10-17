import type { Metadata } from "next";
import { LabView } from "@/components/views/lab";

export const metadata: Metadata = { title: "Model Lab" };

export default function Page() {
  return <LabView />;
}
