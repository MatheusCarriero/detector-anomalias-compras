import { COMPARABILITY_FIELDS } from './statistics/manual-comparability.js';

export const PRICE_REVIEW_CONTRACT = 'p4-price-review/1.0';
export interface PersistedPriceReview {
  contract: typeof PRICE_REVIEW_CONTRACT; mode: 'persisted'; status: 'unavailable';
  purchase: { id: string; version_id: string; content_sha256: string; unit_price: string; currency: 'BRL' };
  metadata_status: 'absent' | 'incomplete' | 'unverified';
  metadata_revision: { id: string; revision: number; content_sha256: string } | null;
  missing_fields: string[]; unverified_fields: string[];
  history: 'not_assessed'; reason: 'manual_contract_and_historical_evidence_required';
}
export interface SimulatedPriceReview {
  contract: typeof PRICE_REVIEW_CONTRACT; mode: 'simulation'; status: 'available';
  origin: 'synthetic-experiment'; scenario_id: 'experiment-prod-cimento-candidate';
  unit_price: string; median_unit_price: string; percent_difference: string;
  percent_fraction: { numerator: string; denominator: string };
  references: number; dates: number; suppliers: number; minimum_references: 20;
  window: { startDate: string; endExclusive: string; days: 90 }; reference_ids: string[];
}
// Read-only transport boundary shared by the API and the restricted proxy.
// It validates shape/provenance; canonical calculations live only in analyzePrice.
export function readPriceReview(value: unknown, target: string): PersistedPriceReview | SimulatedPriceReview | null {
  const obj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
  const exact = (v: Record<string, unknown>, names: string) => Object.keys(v).sort().join(',') === names.split(' ').sort().join(',');
  const match = (v: unknown, pattern: RegExp) => typeof v === 'string' && pattern.exec(v)?.[0] === v;
  const uuid = (v: unknown) => match(v, /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/);
  const hash = (v: unknown) => match(v, /^[a-f0-9]{64}$/);
  const fields = (v: unknown) => Array.isArray(v) && new Set(v).size === v.length && v.every(f => (COMPARABILITY_FIELDS as readonly unknown[]).includes(f));
  if (!obj(value) || value.contract !== PRICE_REVIEW_CONTRACT) return null;
  if (target !== 'simulation') {
    if (!exact(value, 'contract mode status purchase metadata_status metadata_revision missing_fields unverified_fields history reason') ||
      value.mode !== 'persisted' || value.status !== 'unavailable' || value.history !== 'not_assessed' ||
      value.reason !== 'manual_contract_and_historical_evidence_required' ||
      typeof value.metadata_status !== 'string' || !['absent', 'incomplete', 'unverified'].includes(value.metadata_status) || !fields(value.missing_fields) || !fields(value.unverified_fields)) return null;
    const p = value.purchase; const m = value.metadata_revision;
    if (!obj(p) || !exact(p, 'id version_id content_sha256 unit_price currency') || p.id !== target || !uuid(p.id) || !uuid(p.version_id) || !hash(p.content_sha256) ||
      p.currency !== 'BRL' || !match(p.unit_price, /^(0|[1-9]\d{0,6})\.\d{2}$/) || Number(p.unit_price) <= 0 || Number(p.unit_price) > 1_000_000) return null;
    if (m !== null && (!obj(m) || !exact(m, 'id revision content_sha256') || !uuid(m.id) || !hash(m.content_sha256) || !Number.isSafeInteger(m.revision) || Number(m.revision) < 1)) return null;
    if ((value.metadata_status === 'absent') !== (m === null)) return null;
    return value as unknown as PersistedPriceReview;
  }
  if (!exact(value, 'contract mode status origin scenario_id unit_price median_unit_price percent_difference percent_fraction references dates suppliers minimum_references window reference_ids') ||
    value.mode !== 'simulation' || value.status !== 'available' || value.origin !== 'synthetic-experiment' || value.scenario_id !== 'experiment-prod-cimento-candidate' ||
    value.minimum_references !== 20 || !match(value.unit_price, /^\d{1,7}\.\d{2}$/) || !match(value.median_unit_price, /^\d{1,7}\.\d{3}$/) ||
    Number(value.unit_price) <= 0 || Number(value.median_unit_price) <= 0 || !match(value.percent_difference, /^-?\d{1,12}\.\d{6}$/)) return null;
  const fraction = value.percent_fraction; const w = value.window;
  if (!obj(fraction) || !exact(fraction, 'numerator denominator') || !match(fraction.numerator, /^-?\d{1,20}$/) || !match(fraction.denominator, /^[1-9]\d{0,19}$/) ||
    !obj(w) || !exact(w, 'startDate endExclusive days') || w.days !== 90 || w.startDate !== '2026-01-01' || w.endExclusive !== '2026-04-01' ||
    value.references !== 30 || value.dates !== 30 || value.suppliers !== 3 || !Array.isArray(value.reference_ids) || value.reference_ids.length !== 30 ||
    value.reference_ids.some((id, index) => id !== `experiment-prod-cimento-reference-${String(index).padStart(2, '0')}`)) return null;
  return value as unknown as SimulatedPriceReview;
}

export const PRICE_SIMULATION_CONTRACT = 'p4-hypothetical-price/1.0';
export function validCandidatePrice(value: unknown): value is string {
  if (typeof value !== 'string' || /^(0|[1-9]\d{0,6})\.\d{2}$/.exec(value)?.[0] !== value) return false;
  const cents = BigInt(value.replace('.', ''));
  return cents > 0n && cents <= 100_000_000n;
}
export function readHypotheticalPrice(value: unknown, price: string) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (Object.keys(v).sort().join(',') !== 'contract,result' || v.contract !== PRICE_SIMULATION_CONTRACT || !validCandidatePrice(price)) return null;
  const result = readPriceReview(v.result, 'simulation');
  return result?.mode === 'simulation' && result.unit_price === price ? { contract: PRICE_SIMULATION_CONTRACT, result } : null;
}
