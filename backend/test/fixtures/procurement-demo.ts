// Synthetic transport fixtures; no scientific data or model execution.
export const contract = 'procurement-demo/1.0';
export const protocol = 'procurement-demo-cli/1.0';
export const hash = 'fba22a467e5dd800a0af960930d2ca5e2ecbd9d2bc747e37304867d8d031ae21';
export const identities = [
  ['PO-2025-27239', '2025-01-23'], ['PO-2025-34347', '2025-07-15'],
  ['PO-2025-40702', '2025-12-24'], ['PO-2026-40862', '2026-01-16'],
  ['PO-2026-43834', '2026-03-11'], ['PO-2026-47088', '2026-06-17'],
  ['PO-2025-28121', '2025-01-04'],
].map(([po_id, order_date]) => ({ po_id, order_date, occurrence: 1 }));
export const featureNames = [
  'price_to_item_median_90d', 'quantity_to_item_median_90d',
  'item_price_relative_iqr_90d', 'supplier_item_lines_90d', 'business_unit_lines_90d',
];
export const diagnosticNames = [
  'price_to_item_median_90d', 'price_iqr_distance_90d', 'item_price_relative_iqr_90d',
  'quantity_to_item_median_90d', 'total_to_item_median_90d',
  'price_to_supplier_item_median_90d', 'supplier_lines_90d',
  'supplier_item_lines_90d', 'business_unit_lines_90d',
];
export function preparationRequest(unavailable = false) {
  return { contract, source_sha256: hash, operation: { ...identities[unavailable ? 6 : 0] } };
}
function source() {
  return { source_id: 'procurement-spend', source_version: hash,
    entity_namespace: 'procurement-spend-synthetic', origin: 'synthetic',
    monetary_unit: 'unspecified_source_unit', temporal_assumption: 'available_at_order_no_revisions' };
}
function context() {
  return { supplier_id: 'SYN-1', supplier_name: 'Synthetic supplier', supplier_country: 'XX',
    category: 'Synthetic', item: 'Synthetic item', business_unit: 'Demo',
    unit_price: '10.00', quantity: 2, line_total: '20.00' };
}
export function catalog() {
  return { contract, source: source(), operations: identities.map(operation => ({ operation: { ...operation }, context: context() })) };
}
export function prepared(unavailable = false) {
  const count = unavailable ? 17 : 20;
  const features: Record<string, number | null> = {};
  const reasons: Record<string, string | null> = {};
  for (const [i, name] of diagnosticNames.entries()) {
    features[name] = i >= 6 ? count : unavailable || i === 1 ? null : i === 2 ? 0 : 1;
    reasons[name] = features[name] === null ? unavailable ? 'insufficient_history' : 'zero_iqr' : null;
  }
  const stats = () => unavailable ? null : { q1: 10, median: 10, q3: 10, iqr: 0, mad: 0 };
  const operation = preparationRequest(unavailable).operation;
  return {
    contract, source: source(), operation, context: context(), status: unavailable ? 'unavailable' : 'eligible',
    feature_contract: 'procurement-temporal-features/1.0', matrix_contract: 'procurement-experimental-matrix/1.0',
    cutoff_date: operation.order_date,
    window: { start: unavailable ? '2024-10-06' : '2024-10-25', end: operation.order_date, end_exclusive: true },
    coverage: { start_date: '2023-01-01', end_date: '2026-06-30', complete: true, status: 'complete' },
    support: { window: count, item: count, supplier: count, supplier_item: count, business_unit: count },
    feature_names: [...featureNames], values: unavailable ? null : [1, 1, 0, count, count],
    unavailability: Object.fromEntries(featureNames.filter(name => features[name] === null).map(name => [name, reasons[name]])),
    diagnostics: { feature_names: [...diagnosticNames], features, unavailability: reasons,
      references: { item: { unit_price: stats(), quantity: stats(), line_total: stats() }, supplier_item: { unit_price: stats() } } },
  };
}
export function packet(result: unknown) { return JSON.stringify({ protocol, status: 'ok', result }); }
export function failure(status: string, error: string) { return JSON.stringify({ protocol, status, error }); }
