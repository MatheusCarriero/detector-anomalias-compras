import { BadGatewayException, BadRequestException, ServiceUnavailableException } from '@nestjs/common';

// Transport pins mirror P5.15.1/P5.15.2; Python remains responsible for source
// integrity, temporal preparation and all scientific formulas.
export const CONTRACT = 'procurement-demo/1.0';
export const PROTOCOL = 'procurement-demo-cli/1.0';
export const INFERENCE_PROTOCOL = 'procurement-demo-cli/1.1';
export const INFERENCE_CONTRACT = 'procurement-demo-inference/1.0';
// P5.14 release pins, identical to artifact.py; never inferred from a response.
export const MODEL = {
  domain: 'procurement_v2', artifact_id: 'procurement_v2_isolation_forest_p5_9_v1',
  model_sha256: 'fa9f21654626307cf139574707fccae543d9f18ea6f6fa272b8c3053b34bc56d',
  metadata_sha256: '3a78f5014c24cbb3da3bf9e83955b6866b4d18d309fec50cf0efcb779f6a2ed1',
};
export const SOURCE_SHA256 = 'fba22a467e5dd800a0af960930d2ca5e2ecbd9d2bc747e37304867d8d031ae21';
const SOURCE = {
  source_id: 'procurement-spend', source_version: SOURCE_SHA256,
  entity_namespace: 'procurement-spend-synthetic', origin: 'synthetic',
  monetary_unit: 'unspecified_source_unit', temporal_assumption: 'available_at_order_no_revisions',
};
export const OPERATIONS = [
  ['PO-2025-27239', '2025-01-23'], ['PO-2025-34347', '2025-07-15'],
  ['PO-2025-40702', '2025-12-24'], ['PO-2026-40862', '2026-01-16'],
  ['PO-2026-43834', '2026-03-11'], ['PO-2026-47088', '2026-06-17'],
  ['PO-2025-28121', '2025-01-04'],
] as const;
export const FEATURES = [
  'price_to_item_median_90d', 'quantity_to_item_median_90d',
  'item_price_relative_iqr_90d', 'supplier_item_lines_90d', 'business_unit_lines_90d',
] as const;
const DIAGNOSTICS = [
  'price_to_item_median_90d', 'price_iqr_distance_90d', 'item_price_relative_iqr_90d',
  'quantity_to_item_median_90d', 'total_to_item_median_90d',
  'price_to_supplier_item_median_90d', 'supplier_lines_90d',
  'supplier_item_lines_90d', 'business_unit_lines_90d',
] as const;
const REASONS = ['insufficient_history', 'zero_denominator', 'zero_iqr', 'partial_window', 'missing_history'];
export type Action = 'catalog' | 'prepare' | 'run';
export interface OperationIdentity { po_id: string; order_date: string; occurrence: number }

function check(condition: unknown): asserts condition {
  if (!condition) throw new BadGatewayException('PROCUREMENT_INVALID_RESPONSE');
}
function object(value: unknown, keys: readonly string[]): Record<string, unknown> {
  check(value !== null && typeof value === 'object' && !Array.isArray(value));
  check(Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key)));
  return value as Record<string, unknown>;
}
function finite(value: unknown): value is number { return typeof value === 'number' && Number.isFinite(value); }
function count(value: unknown): value is number { return finite(value) && Number.isSafeInteger(value) && value >= 0; }
function names(value: unknown, expected: readonly string[]) {
  check(Array.isArray(value) && value.length === expected.length && value.every((name, i) => name === expected[i]));
}
function identity(value: unknown): OperationIdentity {
  const op = object(value, ['po_id', 'order_date', 'occurrence']);
  check(op.occurrence === 1 && OPERATIONS.some(([id, day]) => op.po_id === id && op.order_date === day));
  return { po_id: op.po_id as string, order_date: op.order_date as string, occurrence: 1 };
}
export function validateRequest(value: unknown) {
  try {
    const req = object(value, ['contract', 'source_sha256', 'operation']);
    check(req.contract === CONTRACT && req.source_sha256 === SOURCE_SHA256);
    return { contract: CONTRACT, source_sha256: SOURCE_SHA256, operation: identity(req.operation) };
  } catch { throw new BadRequestException('PROCUREMENT_INVALID_REQUEST'); }
}
function context(value: unknown) {
  const fields = ['supplier_id', 'supplier_name', 'supplier_country', 'category', 'item', 'business_unit', 'unit_price', 'line_total'];
  const ctx = object(value, [...fields, 'quantity']);
  for (const field of fields) {
    const text = ctx[field];
    check(typeof text === 'string' && text.length > 0 && text.length <= 512 && text.trim() === text);
    for (const char of text) check(char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127);
  }
  for (const field of ['unit_price', 'line_total']) {
    check(/^\d+(?:\.\d+)?$/.test(ctx[field] as string) && Number.isFinite(Number(ctx[field])) && Number(ctx[field]) > 0);
  }
  check(count(ctx.quantity) && ctx.quantity > 0);
}
function source(value: unknown) {
  const src = object(value, Object.keys(SOURCE));
  check(Object.entries(SOURCE).every(([key, expected]) => src[key] === expected));
}
function reference(value: unknown) {
  if (value === null) return;
  const stats = object(value, ['q1', 'median', 'q3', 'iqr', 'mad']);
  for (const item of Object.values(stats)) check(finite(item) && item >= 0);
  check((stats.q1 as number) <= (stats.median as number) && (stats.median as number) <= (stats.q3 as number));
}
function preparation(result: Record<string, unknown>, expected?: OperationIdentity) {
  const op = identity(result.operation);
  check(expected && op.po_id === expected.po_id && op.order_date === expected.order_date && op.occurrence === expected.occurrence);
  context(result.context);
  check(result.feature_contract === 'procurement-temporal-features/1.0' && result.matrix_contract === 'procurement-experimental-matrix/1.0');
  check(result.cutoff_date === op.order_date);
  const window = object(result.window, ['start', 'end', 'end_exclusive']);
  const start = new Date(`${op.order_date}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 90);
  check(window.start === start.toISOString().slice(0, 10) && window.end === op.order_date && window.end_exclusive === true);
  const coverage = object(result.coverage, ['start_date', 'end_date', 'complete', 'status']);
  check(coverage.start_date === '2023-01-01' && coverage.end_date === '2026-06-30' && coverage.complete === true && coverage.status === 'complete');
  const support = object(result.support, ['window', 'item', 'supplier', 'supplier_item', 'business_unit']);
  for (const item of Object.values(support)) check(count(item) && item <= (support.window as number));
  check((support.supplier_item as number) <= (support.supplier as number) && (support.supplier_item as number) <= (support.item as number));
  names(result.feature_names, FEATURES);
  const diag = object(result.diagnostics, ['feature_names', 'features', 'unavailability', 'references']);
  names(diag.feature_names, DIAGNOSTICS);
  const values = object(diag.features, DIAGNOSTICS);
  const reasons = object(diag.unavailability, DIAGNOSTICS);
  for (const [i, name] of DIAGNOSTICS.entries()) {
    const value = values[name];
    if (value === null) check(typeof reasons[name] === 'string' && REASONS.includes(reasons[name] as string));
    else {
      check(finite(value) && reasons[name] === null);
      if (i >= 6) check(count(value));
      else if (i !== 1) check(i === 2 ? value >= 0 : value > 0);
    }
  }
  for (const [i, group] of ['supplier', 'supplier_item', 'business_unit'].entries()) {
    check(values[DIAGNOSTICS[i + 6]] === support[group]);
  }
  const refs = object(diag.references, ['item', 'supplier_item']);
  const itemRefs = object(refs.item, ['unit_price', 'quantity', 'line_total']);
  Object.values(itemRefs).forEach(reference);
  reference(object(refs.supplier_item, ['unit_price']).unit_price);
  const missing = FEATURES.filter(name => values[name] === null);
  const unavailable = object(result.unavailability, missing);
  check(missing.every(name => unavailable[name] === reasons[name]));
  if (missing.length) check(result.status === 'unavailable' && result.values === null);
  else {
    check(result.status === 'eligible' && Array.isArray(result.values) && result.values.length === FEATURES.length);
    check(result.values.every((value, i) => finite(value) && value === values[FEATURES[i]]));
  }
}

// Only validated adapter payloads reach HTTP; stderr/driver text never does.
export function parseResponse(stdout: string, exit: number, action: Action, expected?: OperationIdentity): Record<string, unknown> {
  const protocol = action === 'run' ? INFERENCE_PROTOCOL : PROTOCOL;
  let parsed: unknown;
  try { parsed = JSON.parse(stdout); }
  catch { throw new BadGatewayException('PROCUREMENT_INVALID_RESPONSE'); }
  check(parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed));
  const status = (parsed as Record<string, unknown>).status;
  if (status !== 'ok') {
    const err = object(parsed, ['protocol', 'status', 'error']);
    check(err.protocol === protocol && typeof err.error === 'string');
    if (status === 'invalid_request' && exit === 2) {
      check(['CLI_ARGUMENTS', 'CLI_INPUT_SIZE', 'CLI_JSON', 'CLI_REQUEST', 'CLI_PROTOCOL', 'CLI_ACTION'].includes(err.error));
      throw new BadRequestException('PROCUREMENT_INVALID_REQUEST');
    }
    check(status === 'technical_error' && exit === 1);
    const runErrors = action === 'run' ? ['CLI_PREPARATION_INVALID', 'CLI_MODEL_UNAVAILABLE', 'CLI_MODEL_INTEGRITY',
      'CLI_MODEL_INCOMPATIBLE', 'CLI_MODEL_LOAD_FAILED', 'CLI_INVALID_SCORE', 'CLI_SCORING_FAILED'] : [];
    check(['CLI_OUTPUT_SIZE', 'CLI_FAILURE', 'CLI_SOURCE_HASH', 'CLI_SOURCE_PATH', 'CLI_SOURCE_UNAVAILABLE', 'CLI_ADAPTER_FAILURE', ...runErrors].includes(err.error));
    if (err.error === 'CLI_SOURCE_UNAVAILABLE' || err.error === 'CLI_MODEL_UNAVAILABLE') {
      throw new ServiceUnavailableException(`PROCUREMENT_${err.error.slice(4)}`);
    }
    throw new BadGatewayException(`PROCUREMENT_${err.error.slice(4)}`);
  }
  const envelope = object(parsed, ['protocol', 'status', 'result']);
  check(envelope.protocol === protocol && exit === 0);
  if (action === 'run') return inference(envelope.result, expected);
  return adapterResult(envelope.result, action, expected);
}

function adapterResult(payload: unknown, action: 'catalog' | 'prepare', expected?: OperationIdentity) {
  const keys = action === 'catalog' ? ['operations'] : [
    'operation', 'context', 'status', 'feature_contract', 'matrix_contract', 'cutoff_date',
    'window', 'coverage', 'support', 'feature_names', 'values', 'unavailability', 'diagnostics',
  ];
  const result = object(payload, ['contract', 'source', ...keys]);
  check(result.contract === CONTRACT);
  source(result.source);
  if (action === 'catalog') {
    check(Array.isArray(result.operations) && result.operations.length === OPERATIONS.length);
    result.operations.forEach((value, i) => {
      const entry = object(value, ['operation', 'context']);
      const op = identity(entry.operation);
      check(op.po_id === OPERATIONS[i][0] && op.order_date === OPERATIONS[i][1]);
      context(entry.context);
    });
  } else preparation(result, expected);
  return result;
}

function inference(payload: unknown, expected?: OperationIdentity) {
  const result = object(payload, ['contract', 'preparation', 'status', 'anomaly_score', 'model',
    'score_convention', 'score_semantics', 'score_direction']);
  check(result.contract === INFERENCE_CONTRACT && result.score_convention === '-score_samples'
    && result.score_semantics === 'statistical_anomaly' && result.score_direction === 'higher_is_more_anomalous');
  const prepared = adapterResult(result.preparation, 'prepare', expected);
  if (prepared.status === 'unavailable') {
    check(result.status === 'unavailable' && result.anomaly_score === null && result.model === null);
  } else {
    check(result.status === 'scored' && finite(result.anomaly_score));
    const model = object(result.model, Object.keys(MODEL));
    check(Object.entries(MODEL).every(([key, value]) => model[key] === value));
  }
  return result;
}
