import type { Metadata } from "next";

import { ReplayWorkspace } from "@/components/replay-workspace";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Replay histórico" };

export default function ReplayPage() {
  return <><SiteHeader /><ReplayWorkspace /></>;
}
