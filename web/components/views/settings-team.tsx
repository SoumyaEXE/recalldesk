"use client";

import { RiMailSendLine, RiShieldUserLine, RiUserAddLine } from "@remixicon/react";
import { Avatar } from "@/components/base/avatar/avatar";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { Card, CardHeader, DemoBadge, Pill } from "@/components/ui/surface";
import { DataTable, RowTitle, type Column } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { useShop } from "@/lib/shop";

interface Member {
  name: string;
  email: string;
  role: "Owner" | "Intake" | "Volunteer";
  gets: string;
  last: string;
  color: "blue" | "lime" | "pink" | "neutral";
}

const MEMBERS: Member[] = [
  { name: "Maya Okafor", email: "maya@", role: "Owner", gets: "Card + billing", last: "Today", color: "blue" },
  { name: "Sam Reyes", email: "sam@", role: "Intake", gets: "Card every Thursday", last: "Yesterday", color: "lime" },
  { name: "Priya Natarajan", email: "priya@", role: "Volunteer", gets: "Event cards only", last: "Sep 19", color: "pink" },
];

export function TeamView() {
  const shop = useShop();
  const domain = shop.email.split("@")[1];
  const demo = () => toast({ title: "Invites are a demo", description: "Team accounts aren't wired to a backend yet. Print the card and pin it by the intake desk instead.", status: "information" });
  const columns: Column<Member>[] = [
    { id: "name", header: "Member", mobile: "primary", width: "38%", sort: (m) => m.name, cell: (m) => <RowTitle leading={<Avatar size="md" color={m.color} initials={m.name[0]} />} title={m.name} sub={`${m.email}${domain}`} /> },
    { id: "role", header: "Role", mobile: "badge", width: "16%", sort: (m) => m.role, cell: (m) => <Pill size="sm" tone={m.role === "Owner" ? "blue" : m.role === "Intake" ? "green" : "gray"} dot>{m.role}</Pill> },
    { id: "gets", header: "Receives", mobile: "meta", width: "26%", cell: (m) => <span className="text-body-2-regular text-text-secondary">{m.gets}</span> },
    { id: "last", header: "Last active", mobile: "meta", width: "20%", cell: (m) => <span className="text-body-2-medium text-text-primary">{m.last}</span> },
  ];
  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Settings
            </Pill>
            <DemoBadge>Demo members</DemoBadge>
          </>
        }
        title="Team"
        description={`Who at ${shop.short} gets the Thursday card, and who can correct it. Corrections from anyone become shop memory.`}
        actions={
          <Button leadingIcon={RiUserAddLine} onClick={demo}>
            Invite member
          </Button>
        }
      />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card>
          <CardHeader title="Members" description={`${MEMBERS.length} people`} />
          <div className="border-t border-line">
            <DataTable caption="Team members" rows={MEMBERS} columns={columns} rowKey={(m) => m.name} />
          </div>
        </Card>
        <div className="flex flex-col gap-5">
          <Card className="p-5">
            <RiShieldUserLine className="size-6 text-accent-600" aria-hidden />
            <p className="mt-3 text-headline-semibold text-text-primary">Roles</p>
            <ul className="mt-2 flex flex-col gap-2 text-body-2-regular text-text-secondary">
              <li>
                <span className="font-semibold text-text-primary">Owner</span> · plan, billing, connected services
              </li>
              <li>
                <span className="font-semibold text-text-primary">Intake</span> · runs checks, corrects cards
              </li>
              <li>
                <span className="font-semibold text-text-primary">Volunteer</span> · sees event cards, can tick items as pulled
              </li>
            </ul>
          </Card>
          <Card className="p-5">
            <RiMailSendLine className="size-6 text-accent-600" aria-hidden />
            <p className="mt-3 text-headline-semibold text-text-primary">Thursday email</p>
            <p className="mt-1 text-body-2-regular text-text-secondary">The card goes out as a printable PDF after the 2:00 PM ET sweep, then RecallDesk goes quiet until next Thursday.</p>
          </Card>
        </div>
      </div>
    </Page>
  );
}
