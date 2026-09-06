import { PageHeader } from "@/components/crm/page-header";
import { SourcingMetricForm } from "@/components/crm/sourcing-metric-form";
import { AnalyticsDashboard } from "@/components/crm/analytics-dashboard";

export default function AnalyticsPage() {
  return <>
    <PageHeader eyebrow="Recruiting Analytics" title="Funnel und Conversions" action={<SourcingMetricForm />} />
    <AnalyticsDashboard />
  </>;
}
