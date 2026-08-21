import { SiteHeader } from "@/components/site-header";
import { ValidationWorkspace } from "@/components/validation-workspace";

export const metadata = { title: "Validación científica" };
export default function ValidationPage() {
  return <><SiteHeader /><ValidationWorkspace /></>;
}
