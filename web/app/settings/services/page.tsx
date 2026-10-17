import type { Metadata } from "next";
import { ServicesView } from "@/components/views/settings-services";

export const metadata: Metadata = { title: "Connected services" };

export default function Page() {
  return <ServicesView />;
}
