import { EXPERIMENTAL_PRODUCTS, PRICE_BASIS, SPECIFICATION_CONTRACT } from './experimental-specifications.js';

/** Pure descriptive experiment. No I/O, clock reads, model, DB or Nest provider.
 * availableAt is DECLARED synthetic availability, not proof of a real commit.
 * Coverage is also an explicit experiment assumption, never inferred from rows.
 * All monetary arithmetic and percentage ratios use bigint, not binary floats. */
export const PRICE_ANALYSIS_CONTRACT = 'p4-price-analysis/1.0';
export interface ExperimentalPurchase {
  id: string; productId: string; specificationId: string; unit: string; packaging: string;
  currency: string; priceBasis: string; supplierId: string; departmentId: string;
  quantity: number; unitPrice: string; purchaseDate: string; availableAt: string;
  paymentDays: number; deliveryZone: string;
  quantityPricing: 'independent-by-experiment' | 'same-quantity-only';
}
export interface PriceAnalysisInput {
  contract: typeof PRICE_ANALYSIS_CONTRACT; origin: 'synthetic-experiment'; analysisAt: string;
  operation: ExperimentalPurchase;
  history: { coverage: { startDate: string; endDate: string; complete: boolean }; rows: ExperimentalPurchase[] };
}
type Reason = 'invalid_request' | 'invalid_operation' | 'unsupported_comparability' | 'operation_not_available'
  | 'invalid_history' | 'duplicate_history_identity' | 'incomplete_coverage' | 'no_history' | 'insufficient_history';
interface AnalysisContext {
  operationId: string; analysisAt: string; purpose: 'review_at_analysis_time_not_preapproval';
  specificationContract: string; specificationId: string; productId: string; unit: string; packaging: string;
  currency: 'BRL'; priceBasis: string; paymentDays: number; deliveryZone: string; quantityPricing: string; quantity: number;
  window: { startDate: string; endExclusive: string; days: 90 }; minimumReferences: 20;
  support: { references: number; dates: number; suppliers: number }; referenceIds: string[];
  excluded: { self: number; outside_window: number; not_available: number; incomparable: number };
}
type BaseResult = { contract: typeof PRICE_ANALYSIS_CONTRACT; origin: 'synthetic-experiment' };
export type PriceAnalysisResult = BaseResult & (
  { status: 'unavailable'; reason: Reason; context?: AnalysisContext } |
  { status: 'available'; context: AnalysisContext; unitPrice: string; medianUnitPrice: string;
    constantReferencePrice: boolean; percentDifference: {
      numerator: string; denominator: string; display: string; decimalPlaces: 6; rounding: 'half-away-from-zero';
    } }
);
class Refusal extends Error { constructor(readonly reason: Reason) { super(reason); } }
function requireValue(ok: unknown, reason: Reason): asserts ok { if (!ok) throw new Refusal(reason); }
function object(value: unknown, reason: Reason, keys?: readonly string[]): Record<string, unknown> {
  requireValue(value !== null && typeof value === 'object' && !Array.isArray(value), reason);
  requireValue(Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null, reason);
  const names = Reflect.ownKeys(value);
  requireValue(names.every(key => typeof key === 'string' && Object.hasOwn(Object.getOwnPropertyDescriptor(value, key)!, 'value')), reason);
  if (keys) requireValue(names.length === keys.length && keys.every(key => Object.hasOwn(value, key)), reason);
  return value as Record<string, unknown>;
}
function text(value: unknown, reason: Reason): asserts value is string {
  requireValue(typeof value === 'string' && value.length > 0 && value.length <= 120 && value.trim() === value
    && !Array.from(value).some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127), reason);
}
function day(value: unknown, reason: Reason): asserts value is string {
  requireValue(typeof value === 'string' && value.length === 10 && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && value.slice(0, 4) !== '0000', reason);
  const instant = Date.parse(`${value}T00:00:00.000Z`);
  requireValue(Number.isFinite(instant) && new Date(instant).toISOString().slice(0, 10) === value, reason);
}
function instant(value: unknown, reason: Reason): asserts value is string {
  requireValue(typeof value === 'string' && value.length === 24 && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)
    && value.slice(0, 4) !== '0000' && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value, reason);
}
function localDay(value: string): string {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value));
  const part = (name: string) => parts.find(p => p.type === name)!.value;
  return `${part('year').padStart(4, '0')}-${part('month')}-${part('day')}`;
}
function money(value: unknown, reason: Reason): bigint {
  text(value, reason);
  requireValue(/^(0|[1-9]\d{0,6})\.\d{2}$/.test(value), reason);
  const cents = BigInt(value.replace('.', ''));
  requireValue(cents > 0n && cents <= 100_000_000n, reason);
  return cents;
}
const ROW_KEYS = ['id', 'productId', 'specificationId', 'unit', 'packaging', 'currency', 'priceBasis', 'supplierId',
  'departmentId', 'quantity', 'unitPrice', 'purchaseDate', 'availableAt', 'paymentDays', 'deliveryZone', 'quantityPricing'];
function purchase(value: unknown, reason: Reason): ExperimentalPurchase {
  const p = object(value, reason, ROW_KEYS);
  for (const key of ROW_KEYS.filter(key => !['quantity', 'paymentDays'].includes(key))) text(p[key], reason);
  requireValue(Number.isSafeInteger(p.quantity) && (p.quantity as number) >= 1 && (p.quantity as number) <= 1_000_000, reason);
  requireValue(Number.isSafeInteger(p.paymentDays) && (p.paymentDays as number) >= 0 && (p.paymentDays as number) <= 3650, reason);
  requireValue(['independent-by-experiment', 'same-quantity-only'].includes(p.quantityPricing as string), reason);
  day(p.purchaseDate, reason); instant(p.availableAt, reason); money(p.unitPrice, reason);
  requireValue(p.purchaseDate <= localDay(p.availableAt), reason);
  return p as unknown as ExperimentalPurchase;
}
function shiftedDay(value: string, days: number): string {
  const shifted = new Date(Date.parse(`${value}T00:00:00.000Z`) + days * 86_400_000).toISOString().slice(0, 10);
  day(shifted, 'invalid_operation'); return shifted;
}
function gcd(a: bigint, b: bigint): bigint {
  a = a < 0n ? -a : a;
  while (b) { const remainder = a % b; a = b; b = remainder; }
  return a;
}
function percent(numerator: bigint, denominator: bigint) {
  const divisor = gcd(numerator, denominator); numerator /= divisor; denominator /= divisor;
  const absolute = numerator < 0n ? -numerator : numerator;
  const scaled = absolute * 1_000_000n;
  const rounded = scaled / denominator + (2n * (scaled % denominator) >= denominator ? 1n : 0n);
  return { numerator: String(numerator), denominator: String(denominator),
    display: `${numerator < 0n && rounded !== 0n ? '-' : ''}${rounded / 1_000_000n}.${String(rounded % 1_000_000n).padStart(6, '0')}`,
    decimalPlaces: 6 as const, rounding: 'half-away-from-zero' as const };
}
const GROUP_KEYS = ['productId', 'specificationId', 'unit', 'packaging', 'currency', 'priceBasis',
  'paymentDays', 'deliveryZone', 'quantityPricing'] as const;
const base: BaseResult = { contract: PRICE_ANALYSIS_CONTRACT, origin: 'synthetic-experiment' };

export function analyzePrice(input: unknown): PriceAnalysisResult {
  try {
    const request = object(input, 'invalid_request', ['contract', 'origin', 'analysisAt', 'operation', 'history']);
    requireValue(request.contract === PRICE_ANALYSIS_CONTRACT && request.origin === 'synthetic-experiment', 'invalid_request');
    instant(request.analysisAt, 'invalid_request'); const analysisAt = request.analysisAt;
    const operation = purchase(request.operation, 'invalid_operation');
    requireValue(operation.purchaseDate <= localDay(analysisAt), 'invalid_operation');
    requireValue(operation.availableAt <= analysisAt, 'operation_not_available');
    requireValue(operation.currency === 'BRL' && operation.priceBasis === PRICE_BASIS.id && EXPERIMENTAL_PRODUCTS.some(p =>
      p.productId === operation.productId && p.specificationId === operation.specificationId && p.unit === operation.unit
      && p.packaging === operation.packaging), 'unsupported_comparability');
    const startDate = shiftedDay(operation.purchaseDate, -90);
    const history = object(request.history, 'invalid_history', ['coverage', 'rows']);
    const coverage = object(history.coverage, 'invalid_history', ['startDate', 'endDate', 'complete']);
    day(coverage.startDate, 'invalid_history'); day(coverage.endDate, 'invalid_history');
    requireValue(coverage.startDate <= coverage.endDate && typeof coverage.complete === 'boolean', 'invalid_history');
    requireValue(Array.isArray(history.rows) && history.rows.length <= 20_000, 'invalid_history');
    requireValue(coverage.complete && coverage.startDate <= startDate && coverage.endDate >= shiftedDay(operation.purchaseDate, -1), 'incomplete_coverage');
    const excluded = { self: 0, outside_window: 0, not_available: 0, incomparable: 0 };
    const temporal: Record<string, unknown>[] = [];
    for (const value of history.rows) {
      const r = object(value, 'invalid_history'); text(r.id, 'invalid_history');
      if (r.id === operation.id) { excluded.self++; continue; }
      day(r.purchaseDate, 'invalid_history');
      if (r.purchaseDate < startDate || r.purchaseDate >= operation.purchaseDate) { excluded.outside_window++; continue; }
      instant(r.availableAt, 'invalid_history');
      // Strictly before the cutoff: ties have no established availability order.
      if (r.availableAt >= analysisAt) { excluded.not_available++; continue; }
      temporal.push(r);
    }
    temporal.sort((a, b) => (a.id as string) < (b.id as string) ? -1 : (a.id === b.id ? 0 : 1));
    requireValue(new Set(temporal.map(r => r.id)).size === temporal.length, 'duplicate_history_identity');
    const comparable: ExperimentalPurchase[] = [];
    for (const raw of temporal) {
      const r = purchase(raw, 'invalid_history');
      if (GROUP_KEYS.some(key => r[key] !== operation[key]) ||
        (operation.quantityPricing === 'same-quantity-only' && r.quantity !== operation.quantity)) { excluded.incomparable++; continue; }
      comparable.push(r);
    }
    const context: AnalysisContext = {
      operationId: operation.id, analysisAt, purpose: 'review_at_analysis_time_not_preapproval',
      specificationContract: SPECIFICATION_CONTRACT, specificationId: operation.specificationId,
      productId: operation.productId, unit: operation.unit, packaging: operation.packaging, currency: 'BRL',
      priceBasis: operation.priceBasis, paymentDays: operation.paymentDays, deliveryZone: operation.deliveryZone,
      quantityPricing: operation.quantityPricing, quantity: operation.quantity,
      window: { startDate, endExclusive: operation.purchaseDate, days: 90 },
      minimumReferences: 20, support: { references: comparable.length,
        dates: new Set(comparable.map(r => r.purchaseDate)).size, suppliers: new Set(comparable.map(r => r.supplierId)).size },
      referenceIds: comparable.map(r => r.id), excluded,
    };
    if (comparable.length < 20) return { ...base, status: 'unavailable',
      reason: comparable.length ? 'insufficient_history' : 'no_history', context };
    const prices = comparable.map(r => money(r.unitPrice, 'invalid_history')).sort((a, b) => a < b ? -1 : a === b ? 0 : 1);
    const mid = Math.floor(prices.length / 2);
    // Twice the median in cents is always an integer, even for even sample sizes.
    const twiceMedian = prices.length % 2 ? 2n * prices[mid] : prices[mid - 1] + prices[mid];
    const mills = twiceMedian * 5n;
    const numerator = (2n * money(operation.unitPrice, 'invalid_operation') - twiceMedian) * 100n;
    return { ...base, status: 'available', context, unitPrice: operation.unitPrice,
      medianUnitPrice: `${mills / 1000n}.${String(mills % 1000n).padStart(3, '0')}`,
      constantReferencePrice: prices[0] === prices[prices.length - 1], percentDifference: percent(numerator, twiceMedian) };
  } catch (error) {
    return { ...base, status: 'unavailable', reason: error instanceof Refusal ? error.reason : 'invalid_request' };
  }
}
