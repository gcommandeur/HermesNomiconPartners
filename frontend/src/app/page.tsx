import { DashboardCockpit } from "@/components/crm/dashboard-cockpit";
import { getCockpit } from "@/lib/api/queries";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const result = await getCockpit("week");
  return <DashboardCockpit initialCockpit={result.data} initialSource={result.source} initialError={result.error} />;
}
