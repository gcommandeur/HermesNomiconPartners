// NOMICON: Meine Provision - Rang, Fortschritt und nachvollziehbare Rechnung für jeden Mitarbeiter.
import { PageHeader } from "@/components/crm/page-header";
import { MyCommissionView } from "@/components/crm/my-commission";
import { brand } from "@/lib/brand";

export default function MyCommissionPage() {
  return (
    <>
      <PageHeader eyebrow={brand.appName} title="Meine Provision" />
      <MyCommissionView />
    </>
  );
}
