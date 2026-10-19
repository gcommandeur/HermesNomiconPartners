// Aus Hermes übernommen (Paket C3, Fehlerbehebung): Schutz vor CSV-/Formel-Injektion.
// Zellen, die mit "=", "+", "-", "@", Tabulator oder Zeilenumbruch beginnen, würde Excel/LibreOffice
// beim Öffnen als Formel ausführen. Ein vorangestelltes Apostroph macht daraus Text. Ausnahme: reine
// Zahlen- und Telefonmuster ("-5", "+49 170 123-45") bleiben lesbar; sie enthalten außer dem führenden
// Vorzeichen keine Formelzeichen. Als reine Funktion ausgelagert (testbar ohne Komponenten).

export function neutralizeFormula(text: string): string {
  if (!/^[=+\-@\t\r]/.test(text)) return text;
  if (/^[+-][\d\s().\/-]+$/.test(text)) return text;
  return `'${text}`;
}
