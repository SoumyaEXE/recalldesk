import type { Metadata } from "next";
import { TeamView } from "@/components/views/settings-team";

export const metadata: Metadata = { title: "Team" };

export default function Page() {
  return <TeamView />;
}
