"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { getCustomFields, saveCustomFieldValues } from "@/lib/api/queries";
import type { CustomFieldDefinition, CustomFieldEntity, CustomFieldValue } from "@/lib/api/types";

const selectClass =
  "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";

/** Eigene Felder (vom Admin unter Einstellungen → Eigene Felder angelegt) an
 * Kandidat bzw. Kunde: zeigt alle aktiven Felder und speichert die Werte. Ohne
 * definierte Felder wird nichts angezeigt. */
export function CustomFieldsPanel({
  entityType,
  entityId,
  initialValues,
}: {
  entityType: CustomFieldEntity;
  entityId: string;
  initialValues: Record<string, CustomFieldValue> | undefined;
}) {
  const [definitions, setDefinitions] = useState<CustomFieldDefinition[]>([]);
  const [values, setValues] = useState<Record<string, CustomFieldValue>>(initialValues ?? {});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCustomFields(entityType).then((result) => {
      if (!cancelled) setDefinitions(result.data);
    });
    return () => {
      cancelled = true;
    };
  }, [entityType]);

  if (definitions.length === 0) return null;

  function setValue(key: string, value: CustomFieldValue) {
    setMessage(null);
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function handleSave() {
    setBusy(true);
    setMessage(null);
    try {
      const saved = await saveCustomFieldValues(entityType, entityId, values);
      setValues(saved.custom_fields);
      setMessage("Gespeichert.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-6">
      <CardContent className="space-y-4">
        <p className="text-sm font-semibold">Eigene Felder</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {definitions.map((definition) => {
            const value = values[definition.key] ?? null;
            return (
              <label key={definition.id} className="block text-xs text-brand-muted">
                <span className="mb-1 block">{definition.label}</span>
                {definition.field_type === "boolean" ? (
                  <select
                    className={selectClass}
                    value={value === null ? "" : value ? "ja" : "nein"}
                    onChange={(event) =>
                      setValue(definition.key, event.target.value === "" ? null : event.target.value === "ja")
                    }
                  >
                    <option value="">–</option>
                    <option value="ja">Ja</option>
                    <option value="nein">Nein</option>
                  </select>
                ) : definition.field_type === "select" ? (
                  <select
                    className={selectClass}
                    value={typeof value === "string" ? value : ""}
                    onChange={(event) => setValue(definition.key, event.target.value || null)}
                  >
                    <option value="">–</option>
                    {definition.options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : definition.field_type === "number" ? (
                  <Input
                    type="number"
                    value={typeof value === "number" ? value : ""}
                    onChange={(event) =>
                      setValue(definition.key, event.target.value === "" ? null : Number(event.target.value))
                    }
                  />
                ) : (
                  <Input
                    type={definition.field_type === "date" ? "date" : "text"}
                    value={typeof value === "string" ? value : ""}
                    onChange={(event) => setValue(definition.key, event.target.value || null)}
                  />
                )}
              </label>
            );
          })}
        </div>
        <div className="flex items-center gap-3">
          <Button size="sm" disabled={busy} onClick={() => void handleSave()}>
            Speichern
          </Button>
          {message && <span className="text-xs text-brand-muted">{message}</span>}
        </div>
      </CardContent>
    </Card>
  );
}
