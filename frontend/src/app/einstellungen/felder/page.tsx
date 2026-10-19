"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/lib/api/hooks";
import { createCustomField, getCustomFields, updateCustomField } from "@/lib/api/queries";
import type { CustomFieldDefinition, CustomFieldEntity, CustomFieldType } from "@/lib/api/types";

const selectClass =
  "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";

const ENTITY_LABELS: Record<CustomFieldEntity, string> = {
  candidate: "Kandidaten",
  client: "Kunden",
  contact: "Kontakte",
};

const TYPE_LABELS: Record<CustomFieldType, string> = {
  text: "Text",
  number: "Zahl",
  date: "Datum",
  boolean: "Ja/Nein",
  select: "Auswahl",
};

export default function EigeneFelderPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const [fields, setFields] = useState<CustomFieldDefinition[]>([]);
  const [entity, setEntity] = useState<CustomFieldEntity>("candidate");
  const [label, setLabel] = useState("");
  const [type, setType] = useState<CustomFieldType>("text");
  const [options, setOptions] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await getCustomFields(undefined, true);
    setFields(result.data);
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    void load();
  }, [isAdmin, load]);

  async function run(action: () => Promise<void>) {
    setMessage(null);
    try {
      await action();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Aktion fehlgeschlagen.");
    }
  }

  if (meLoading) {
    return <div className="h-16 animate-pulse rounded-lg bg-brand-surface" />;
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Einstellungen" title="Eigene Felder" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-brand-muted">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Einstellungen" title="Eigene Felder" />
      <p className="mb-5 max-w-3xl text-sm text-brand-muted">
        Zusätzliche Felder für Kandidaten, Kunden und Kontakte – ohne Programmierung. Sie erscheinen auf der
        Detailseite im Block „Eigene Felder“ und lassen sich in der Kandidatenliste per Auswahl-/Ja-Nein-Wert
        filtern. Typ und Schlüssel sind nach dem Anlegen fest; ein Feld wird deaktiviert statt gelöscht, damit
        gespeicherte Werte erhalten bleiben.
      </p>

      <Card className="mb-5">
        <CardContent className="grid gap-3 md:grid-cols-5">
          <select className={selectClass} value={entity} onChange={(event) => setEntity(event.target.value as CustomFieldEntity)}>
            {(Object.keys(ENTITY_LABELS) as CustomFieldEntity[]).map((key) => (
              <option key={key} value={key}>{ENTITY_LABELS[key]}</option>
            ))}
          </select>
          <Input placeholder="Bezeichnung" value={label} onChange={(event) => setLabel(event.target.value)} />
          <select className={selectClass} value={type} onChange={(event) => setType(event.target.value as CustomFieldType)}>
            {(Object.keys(TYPE_LABELS) as CustomFieldType[]).map((key) => (
              <option key={key} value={key}>{TYPE_LABELS[key]}</option>
            ))}
          </select>
          <Input
            placeholder="Optionen, kommagetrennt"
            disabled={type !== "select"}
            value={options}
            onChange={(event) => setOptions(event.target.value)}
          />
          <Button
            disabled={!label.trim()}
            onClick={() =>
              void run(async () => {
                await createCustomField({
                  entity_type: entity,
                  label,
                  field_type: type,
                  options: type === "select" ? options.split(",").map((item) => item.trim()).filter(Boolean) : [],
                });
                setLabel("");
                setOptions("");
              })
            }
          >
            Feld anlegen
          </Button>
        </CardContent>
      </Card>
      {message && <p className="mb-3 text-sm text-red-300">{message}</p>}

      <div className="space-y-3">
        {fields.length === 0 && <p className="text-sm text-brand-muted">Noch keine eigenen Felder.</p>}
        {fields.map((field) => (
          <Card key={field.id}>
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">
                  {field.label}
                  {!field.is_active && <span className="ml-2 text-xs text-brand-muted">(deaktiviert)</span>}
                </p>
                <p className="text-xs text-brand-muted">
                  {ENTITY_LABELS[field.entity_type]} · {TYPE_LABELS[field.field_type]} · Schlüssel {field.key}
                  {field.options.length > 0 && ` · ${field.options.join(", ")}`}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void run(async () => { await updateCustomField(field.id, { is_active: !field.is_active }); })}
              >
                {field.is_active ? "Deaktivieren" : "Aktivieren"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
