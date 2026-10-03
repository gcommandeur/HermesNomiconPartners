/**
 * Compile-Zeit-Abgleich der HAND GESCHRIEBENEN Typen (types.ts) mit den aus dem
 * Backend ERZEUGTEN (schema.d.ts, siehe `pnpm gen:api`). Dieses Modul erzeugt keinen
 * Laufzeitcode - schlaegt nur `pnpm typecheck` fehl, sobald ein Feld
 *   - im Backend nicht (mehr) existiert, oder
 *   - dort einen anderen Typ hat (Aenderung von Enum-Werten, Zahl <-> Text ...).
 * Optional/Pflicht und null/undefined werden bewusst NICHT verglichen: Felder mit
 * Standardwert gelten im OpenAPI-Schema als optional, kommen in Antworten aber immer.
 *
 * Bekannte, noch nicht behobene Abweichungen stehen in den `Known…`-Listen. Wer eine
 * behebt, entfernt den Eintrag (der Typ-Check meldet dann "unnoetig"); neue
 * Abweichungen duerfen NICHT einfach dort eingetragen werden.
 */
import type {
  Candidate,
  CandidateSubmission,
  ClientCompany,
  Contact,
  Fee,
  Interview,
  Offer,
  Placement,
  Task,
} from "./types";
import type { components } from "./schema";

type Schemas = components["schemas"];
type Strip<T> = Exclude<T, null | undefined>;

/** Schluessel von H, die in G fehlen oder deren (bereinigter) Typ nicht passt. */
type Mismatch<H, G> = {
  [K in keyof H]-?: K extends keyof G ? ([Strip<H[K]>] extends [Strip<G[K]>] ? never : K) : K;
}[keyof H];

/** Fehler, wenn `Actual` nicht genau den erwarteten Ausnahmen entspricht. */
type ExpectExactly<Actual, Expected> = [Actual] extends [Expected]
  ? [Expected] extends [Actual]
    ? true
    : { unnoetigeAusnahme: Exclude<Expected, Actual> }
  : { neueAbweichung: Exclude<Actual, Expected> };

/**
 * Bekannte Abweichungen (Stand der Einfuehrung dieses Abgleichs):
 *  - Geldbetraege und Prozentsaetze (`Decimal` im Backend) kommen als TEXT ("12000.00")
 *    an, sind hier aber als `number` deklariert. Anzeige per Intl.NumberFormat vertraegt
 *    Text, Rechnen mit `+` wuerde stillschweigend Text verketten - vor jeder Rechnung
 *    mit Number() umwandeln oder die Typen auf `string` stellen.
 *  - `last_contact`, `size`, `contact_name`, `active_mandates`: nur im Frontend
 *    deklariert, vom Backend nie gesendet (Altlast aus der Demo-Phase); die Oberflaeche
 *    zeigt dafuer nichts bzw. einen Platzhalter.
 */
type KnownCandidate = "last_contact";
type KnownClientCompany =
  | "fee_percentage"
  | "size"
  | "contact_name"
  | "active_mandates"
  | "last_contact";
type KnownSubmission = "fee_percentage" | "expected_fee";
type KnownPlacement =
  | "final_salary"
  | "fee_percentage"
  | "rabatt_percentage"
  | "fee_fix"
  | "calculated_fee";
type KnownOffer = "offered_salary" | "variable_compensation";

type CandidateCheck = ExpectExactly<
  Mismatch<Candidate, Schemas["CandidateRead"]>,
  KnownCandidate
>;
type ClientCompanyCheck = ExpectExactly<
  Mismatch<ClientCompany, Schemas["ClientCompanyRead"]>,
  KnownClientCompany
>;
type ContactCheck = ExpectExactly<Mismatch<Contact, Schemas["ContactPersonRead"]>, never>;
type SubmissionCheck = ExpectExactly<
  Mismatch<CandidateSubmission, Schemas["CandidateSubmissionRead"]>,
  KnownSubmission
>;
type TaskCheck = ExpectExactly<Mismatch<Task, Schemas["TaskRead"]>, never>;
type PlacementCheck = ExpectExactly<Mismatch<Placement, Schemas["PlacementRead"]>, KnownPlacement>;
type FeeCheck = ExpectExactly<Mismatch<Fee, Schemas["FeeRead"]>, never>;
type OfferCheck = ExpectExactly<Mismatch<Offer, Schemas["OfferRead"]>, KnownOffer>;
type InterviewCheck = ExpectExactly<Mismatch<Interview, Schemas["InterviewRead"]>, never>;

const assertTrue = <T extends true>() => undefined as unknown as T;
export const conformance = [
  assertTrue<CandidateCheck>(),
  assertTrue<ClientCompanyCheck>(),
  assertTrue<ContactCheck>(),
  assertTrue<SubmissionCheck>(),
  assertTrue<TaskCheck>(),
  assertTrue<PlacementCheck>(),
  assertTrue<FeeCheck>(),
  assertTrue<OfferCheck>(),
  assertTrue<InterviewCheck>(),
];
